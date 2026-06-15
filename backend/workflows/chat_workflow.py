from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Callable, Optional

try:
    from langgraph.graph import END, START, StateGraph
except Exception:
    START = "__start__"
    END = "__end__"
    StateGraph = None

from backend.rag.metadata_service import normalize_device_model
from backend.services.evidence_service import build_evidence_items, build_grounding_result
from backend.tools.base import ToolResult, sanitize_error
from backend.tools.diagnostics_tool import run_diagnostics_context_tool
from backend.tools.feedback_tool import run_feedback_case_tool
from backend.tools.graphrag_tool import empty_graph_context, run_lazy_graphrag_tool
from backend.tools.rag_tool import apply_device_gate_tool, run_rag_retrieval_tool
from backend.tools.vision_tool import run_vision_context_tool
from backend.workflows.chat_prompts import SYSTEM_PROMPT, build_answer_prompt
from backend.workflows.chat_state import ChatState

NODE_SEQUENCE = [
    "normalize_input_node",
    "parse_query_node",
    "retrieve_context_node",
    "device_gate_node",
    "lazy_graphrag_node",
    "vision_context_node",
    "diagnostics_context_node",
    "feedback_case_node",
    "plan_answer_node",
    "generate_answer_node",
    "format_sources_node",
    "build_tool_trace_node",
    "format_response_node",
]


def run_chat_graph_workflow(
    query: str,
    top_k: int = 5,
    device_model: Optional[str] = None,
    alarm_code: Optional[str] = None,
    image_path: Optional[str] = None,
    request_id: Optional[str] = None,
    mock_llm: Optional[bool] = None,
) -> dict[str, Any]:
    state: ChatState = {
        "request_id": request_id or uuid.uuid4().hex,
        "query": query,
        "device_model": device_model or "",
        "alarm_code": alarm_code or "",
        "image_path": image_path or "",
        "raw_contexts": [],
        "filtered_contexts": [],
        "feedback_cases": [],
        "tool_results": [],
        "tool_trace": [],
        "sources": [],
        "errors": [],
        "timings": {},
        "debug": {"top_k": top_k, "mock_llm": should_mock_llm(mock_llm)},
        "degraded": False,
    }
    graph, workflow_backend, backend_error = build_chat_graph(top_k=top_k, mock_llm=should_mock_llm(mock_llm))
    state["workflow_backend"] = workflow_backend
    state["debug"]["workflow_backend"] = workflow_backend
    if backend_error:
        state["debug"]["workflow_backend_error"] = backend_error
        state["errors"].append({"node": "build_chat_graph", "message": backend_error})
    result = graph.invoke(state)
    return result.get("response", result)


def build_chat_graph(top_k: int = 5, mock_llm: bool = False) -> tuple[Any, str, str]:
    nodes = build_nodes(top_k=top_k, mock_llm=mock_llm)
    if StateGraph is None:
        return SequentialGraph(nodes), "sequential_fallback", "langgraph is not installed"

    try:
        graph = StateGraph(ChatState)
        for name in NODE_SEQUENCE:
            graph.add_node(name, nodes[name])
        graph.add_edge(START, NODE_SEQUENCE[0])
        for left, right in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:]):
            graph.add_edge(left, right)
        graph.add_edge(NODE_SEQUENCE[-1], END)
        return graph.compile(), "langgraph", ""
    except Exception as exc:
        return SequentialGraph(nodes), "sequential_fallback", f"LangGraph build failed: {sanitize_error(exc)}"


def build_nodes(top_k: int, mock_llm: bool) -> dict[str, Callable[[ChatState], ChatState]]:
    return {
        "normalize_input_node": normalize_input_node,
        "parse_query_node": parse_query_node,
        "retrieve_context_node": lambda state: retrieve_context_node(state, top_k=top_k),
        "device_gate_node": device_gate_node,
        "lazy_graphrag_node": lazy_graphrag_node,
        "vision_context_node": vision_context_node,
        "diagnostics_context_node": diagnostics_context_node,
        "feedback_case_node": feedback_case_node,
        "plan_answer_node": plan_answer_node,
        "generate_answer_node": lambda state: generate_answer_node(state, mock_llm=mock_llm),
        "format_sources_node": format_sources_node,
        "build_tool_trace_node": build_tool_trace_node,
        "format_response_node": format_response_node,
    }


class SequentialGraph:
    def __init__(self, nodes: dict[str, Callable[[ChatState], ChatState]]) -> None:
        self.nodes = nodes

    def invoke(self, state: ChatState) -> ChatState:
        current = dict(state)
        for name in NODE_SEQUENCE:
            current = self.nodes[name](current)
        return current


def normalize_input_node(state: ChatState) -> ChatState:
    return timed_node(state, "normalize_input_node", _normalize_input)


def _normalize_input(state: ChatState) -> ChatState:
    state = ensure_state(state)
    state["query"] = " ".join(str(state.get("query", "")).split())
    state["device_model"] = normalize_device_model(state.get("device_model")) or normalize_device_model(state.get("query"))
    state["alarm_code"] = str(state.get("alarm_code") or "").strip()
    if state.get("alarm_code") and state["alarm_code"] not in state["query"]:
        state["query"] = f"{state['alarm_code']} {state['query']}".strip()
    return state


def parse_query_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        from backend.rag.langchain_pipeline import parse_query_info

        current["query_info"] = parse_query_info(current.get("query", ""), current.get("device_model"))
        return current

    return timed_node(state, "parse_query_node", _run)


def retrieve_context_node(state: ChatState, top_k: int = 5) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        result = run_rag_retrieval_tool(current.get("query", ""), current.get("query_info", {}), top_k=top_k)
        append_tool_result(current, result)
        data = result.get("data", {})
        current["raw_contexts"] = data.get("raw_contexts", []) if result.get("status") != "failed" else []
        current["retrieval_filter"] = data.get("retrieval_filter", {}) if result.get("status") != "failed" else {
            "filter_fallback": True,
            "filter_message": result.get("error") or result.get("summary", "RAG 检索失败"),
        }
        return current

    return timed_node(state, "retrieve_context_node", _run)


def device_gate_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        result = apply_device_gate_tool(
            current.get("raw_contexts", []),
            current.get("device_model"),
            current.get("retrieval_filter", {}),
        )
        append_tool_result(current, result)
        data = result.get("data", {})
        current["filtered_contexts"] = data.get("filtered_contexts", [])
        current["retrieval_filter"] = data.get("retrieval_filter", current.get("retrieval_filter", {}))
        return current

    return timed_node(state, "device_gate_node", _run)


def lazy_graphrag_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        result = run_lazy_graphrag_tool(
            current.get("query", ""),
            current.get("filtered_contexts", []),
            device_model=current.get("device_model"),
        )
        append_tool_result(current, result)
        current["graph_context"] = result.get("data", {}).get("graph_context") or empty_graph_context("图谱节点未执行")
        return current

    return timed_node(state, "lazy_graphrag_node", _run)


def vision_context_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        result = run_vision_context_tool(
            current.get("image_path"),
            current.get("query", ""),
            device_model=current.get("device_model"),
        )
        append_tool_result(current, result)
        current["vision_context"] = result.get("data", {}).get("vision_context", {"enabled": False})
        return current

    return timed_node(state, "vision_context_node", _run)


def diagnostics_context_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        result = run_diagnostics_context_tool(
            current.get("query", ""),
            current.get("filtered_contexts", []),
            current.get("graph_context", {}),
            current.get("vision_context", {}),
        )
        append_tool_result(current, result)
        data = result.get("data", {})
        current["diagnostics_context"] = data.get("diagnostics_context", {})
        current["confidence"] = data.get("confidence", {"level": "low", "score": 0})
        return current

    return timed_node(state, "diagnostics_context_node", _run)


def feedback_case_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        result = run_feedback_case_tool(current.get("query", ""), device_model=current.get("device_model"))
        append_tool_result(current, result)
        current["feedback_cases"] = result.get("data", {}).get("feedback_cases", [])
        return current

    return timed_node(state, "feedback_case_node", _run)


def plan_answer_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        current["answer_plan"] = {
            "priority": ["manual_contexts", "graph_context", "vision_context", "feedback_cases"],
            "manual_context_count": len(current.get("filtered_contexts", [])),
            "use_graph": bool(current.get("graph_context", {}).get("enabled", False)),
            "use_vision": bool(current.get("vision_context", {}).get("enabled", False)),
            "use_feedback": bool(current.get("feedback_cases", [])),
            "must_disclose_fallback": bool(current.get("retrieval_filter", {}).get("filter_fallback", False)),
        }
        return current

    return timed_node(state, "plan_answer_node", _run)


def generate_answer_node(state: ChatState, mock_llm: bool = False) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        prompt = build_answer_prompt(
            query=current.get("query", ""),
            device_model=current.get("device_model", ""),
            query_info=current.get("query_info", {}),
            contexts=current.get("filtered_contexts", []),
            graph_context=current.get("graph_context", {}),
            vision_context=current.get("vision_context", {}),
            feedback_cases=current.get("feedback_cases", []),
            diagnostics_context=current.get("diagnostics_context", {}),
        )
        current.setdefault("debug", {})["answer_prompt_preview"] = prompt[:1200]
        if mock_llm or not has_qwen_api_key():
            current["final_answer"] = build_mock_answer(current)
            current["degraded"] = bool(not current.get("filtered_contexts")) or bool(current.get("retrieval_filter", {}).get("filter_fallback", False))
            return current

        try:
            current["final_answer"] = call_qwen_answer(prompt)
            current["degraded"] = False
        except Exception as exc:
            append_error(current, "generate_answer_node", exc)
            current["final_answer"] = build_mock_answer(current, reason=sanitize_error(exc))
            current["degraded"] = True
        return current

    return timed_node(state, "generate_answer_node", _run)


def format_sources_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        contexts = current.get("filtered_contexts", [])
        evidence_items = build_evidence_items(contexts)
        feedback_sources = [
            {
                "source_type": "feedback_case",
                "case_id": case.get("case_id", ""),
                "title": case.get("title", ""),
                "device_model": case.get("device_model", ""),
                "content": case.get("content", ""),
            }
            for case in current.get("feedback_cases", [])
        ]
        current["sources"] = evidence_items + feedback_sources
        return current

    return timed_node(state, "format_sources_node", _run)


def build_tool_trace_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        current["tool_trace"] = [tool_result_to_trace(result) for result in current.get("tool_results", [])]
        return current

    return timed_node(state, "build_tool_trace_node", _run)


def format_response_node(state: ChatState) -> ChatState:
    def _run(current: ChatState) -> ChatState:
        contexts = current.get("filtered_contexts", [])
        graph_context = current.get("graph_context", {})
        response = {
            "question": current.get("query", ""),
            "answer": current.get("final_answer", ""),
            "structured_answer": parse_structured_answer(current.get("final_answer", "")),
            "contexts": contexts,
            "evidence_items": build_evidence_items(contexts),
            "grounding_result": build_grounding_result(contexts),
            "retrieval_filter": current.get("retrieval_filter", {}),
            "graph_context": graph_context,
            "graph_paths": graph_context.get("paths", []),
            "seed_nodes": graph_context.get("seed_nodes", []),
            "graph_enabled": bool(graph_context.get("enabled", False)),
            "graph_warnings": graph_context.get("warnings", []),
            "tool_trace": current.get("tool_trace", []),
            "sources": current.get("sources", []),
            "degraded": bool(current.get("degraded", False)),
            "model_status": "mocked" if current.get("debug", {}).get("mock_llm") else ("degraded" if current.get("degraded") else "available"),
            "llm_status": "mocked" if current.get("debug", {}).get("mock_llm") else ("degraded" if current.get("degraded") else "available"),
            "errors": current.get("errors", []),
            "request_id": current.get("request_id", ""),
            "workflow_steps": current.get("workflow_steps", []),
            "workflow_backend": current.get("workflow_backend", ""),
            "debug": current.get("debug", {}),
            "confidence": current.get("confidence", {}),
        }
        current["response"] = response
        response["workflow_steps"] = current.get("workflow_steps", [])
        return current

    return timed_node(state, "format_response_node", _run)


def timed_node(state: ChatState, node_name: str, function: Callable[[ChatState], ChatState]) -> ChatState:
    current = ensure_state(state)
    tool_count_before = len(current.get("tool_results", []))
    started_at = time.perf_counter()
    status = "success"
    error = ""
    try:
        return function(current)
    except Exception as exc:
        status = "failed"
        error = sanitize_error(exc)
        append_error(current, node_name, exc)
        current["degraded"] = True
        return current
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        current.setdefault("timings", {})[node_name] = duration_ms
        tool_result = latest_tool_result(current, tool_count_before)
        if tool_result and status != "failed":
            status = str(tool_result.get("status") or "success")
            error = str(tool_result.get("error") or "")
        append_workflow_step(
            current,
            name=workflow_step_name(node_name),
            status=status,
            duration_ms=duration_ms,
            summary=workflow_step_summary(node_name, current, tool_result),
            error=error,
        )
        if current.get("response"):
            current["response"]["workflow_steps"] = current.get("workflow_steps", [])
            current["response"]["workflow_backend"] = current.get("workflow_backend", "")
            current["response"]["debug"] = current.get("debug", {})


def ensure_state(state: ChatState) -> ChatState:
    state.setdefault("tool_results", [])
    state.setdefault("tool_trace", [])
    state.setdefault("errors", [])
    state.setdefault("timings", {})
    state.setdefault("debug", {})
    state.setdefault("workflow_steps", [])
    return state


def latest_tool_result(state: ChatState, tool_count_before: int) -> Optional[ToolResult]:
    tool_results = state.get("tool_results", [])
    if len(tool_results) <= tool_count_before:
        return None
    return tool_results[-1]


def append_workflow_step(
    state: ChatState,
    name: str,
    status: str,
    duration_ms: int,
    summary: str,
    error: str = "",
) -> None:
    step = {
        "name": name,
        "status": status,
        "duration_ms": duration_ms,
        "summary": summary,
        "degraded": bool(state.get("degraded", False)),
    }
    if error:
        step["error"] = error
    state.setdefault("workflow_steps", []).append(step)


def workflow_step_name(node_name: str) -> str:
    return node_name[:-5] if node_name.endswith("_node") else node_name


def workflow_step_summary(
    node_name: str,
    state: ChatState,
    tool_result: Optional[ToolResult],
) -> str:
    if tool_result:
        return str(tool_result.get("summary") or "")
    return {
        "normalize_input_node": "标准化输入和设备型号",
        "parse_query_node": "解析设备型号、报警码、参数和关键词",
        "plan_answer_node": "生成回答计划",
        "generate_answer_node": "生成最终回答",
        "format_sources_node": f"格式化 {len(state.get('sources', []))} 条来源",
        "build_tool_trace_node": f"生成 {len(state.get('tool_trace', []))} 条工具轨迹",
        "format_response_node": "组装前端兼容响应",
    }.get(node_name, "节点执行完成")


def append_tool_result(state: ChatState, result: ToolResult) -> None:
    state.setdefault("tool_results", []).append(result)
    if result.get("status") == "failed":
        state.setdefault("errors", []).append(
            {
                "node": result.get("name", ""),
                "message": result.get("error") or result.get("summary", ""),
            }
        )
        state["degraded"] = True


def append_error(state: ChatState, node_name: str, exc: Exception) -> None:
    state.setdefault("errors", []).append({"node": node_name, "message": sanitize_error(exc)})


def tool_result_to_trace(result: ToolResult) -> dict[str, Any]:
    return {
        "tool_name": result.get("name", ""),
        "display_name": display_name_for_tool(result.get("name", "")),
        "status": result.get("status", "skipped"),
        "input_summary": "",
        "output_summary": result.get("summary", ""),
        "duration_ms": result.get("duration_ms", 0),
        "error": result.get("error"),
        "metadata": result.get("data", {}),
    }


def display_name_for_tool(name: str) -> str:
    return {
        "RagRetrievalTool": "知识检索工具",
        "DeviceGateTool": "设备型号过滤工具",
        "LazyGraphRAGTool": "关联图谱扩展工具",
        "VisionAnalysisTool": "多模态视觉识别工具",
        "DiagnosticsContextTool": "诊断上下文工具",
        "FeedbackCaseTool": "审核案例召回工具",
    }.get(name, name or "WorkflowTool")


def should_mock_llm(mock_llm: Optional[bool]) -> bool:
    if mock_llm is not None:
        return bool(mock_llm)
    return os.getenv("MOCK_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def has_qwen_api_key() -> bool:
    try:
        from backend.core.config import QWEN_API_KEY

        return bool(QWEN_API_KEY)
    except Exception:
        return False


def call_qwen_answer(prompt: str) -> str:
    from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
    from openai import OpenAI

    client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, timeout=30)
    response = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


def build_mock_answer(state: ChatState, reason: str = "") -> str:
    contexts = state.get("filtered_contexts", [])
    graph_context = state.get("graph_context", {})
    diagnostics = state.get("diagnostics_context", {})
    lines = [
        "## 现象判断",
        f"针对 {state.get('device_model') or '未指定设备'} 的问题：{state.get('query', '')}",
    ]
    if not contexts:
        lines.append("现有知识库依据不足，不能作为标准作业依据。")
    elif reason:
        lines.append(f"大模型生成不可用，已基于本地证据返回降级结果：{reason}")
    else:
        lines.append("已基于当前召回的维修手册片段生成模拟回答，测试模式未调用真实大模型。")

    lines.extend(["", "## 可能原因"])
    if contexts:
        for context in contexts[:3]:
            lines.append(f"- 参考 {context.get('pdf_filename') or context.get('filename') or '未知文件'} 第 {context.get('page_number') or context.get('page') or '-'} 页片段。")
    else:
        lines.append("- 手册证据不足，不能确认具体原因。")

    lines.extend(["", "## 排查步骤"])
    lines.append("1. 停机、断电、挂牌，并确认防误启动。")
    lines.append("2. 按维修手册来源逐条核对报警、参数、端子和现场状态。")
    if graph_context.get("enabled"):
        lines.append("3. 将关联知识图谱路径作为辅助排查线索，不替代手册依据。")

    lines.extend(["", "## 引用来源"])
    if contexts:
        for context in contexts[:5]:
            lines.append(
                f"- {context.get('pdf_filename') or context.get('filename') or '未知文件'} "
                f"第 {context.get('page_number') or context.get('page') or '-'} 页 "
                f"chunk_id={context.get('chunk_id') or ''} 设备={context.get('device_model') or '未标注'}"
            )
    else:
        lines.append("- 未命中可用维修手册来源。")

    lines.extend(["", "## 风险提醒"])
    lines.append(f"- 风险等级：{diagnostics.get('risk_level', 'unknown')}。证据不足或高风险时必须由设备工程师复核。")
    lines.append("- 不得根据本回答编造或替换手册中的报警码、参数号、接线端子和页码。")

    lines.extend(["", "## 下一步操作"])
    lines.append("- 优先打开引用手册原页复核，再执行现场检查。")
    return "\n".join(lines)


def parse_structured_answer(answer: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
