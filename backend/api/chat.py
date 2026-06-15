import json
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.rag.langchain_pipeline import run_langchain_chat
from backend.services.evidence_service import build_evidence_items
from backend.services.evidence_service import build_grounding_result
from backend.services.evidence_service import build_retrieval_filter_result
from backend.services.lazy_graphrag_service import build_lazy_graph_context
from backend.services.llm_service import generate_repair_answer
from backend.services.tool_orchestrator_service import build_tool_result
from backend.services.tool_orchestrator_service import elapsed_ms
from backend.services.tool_orchestrator_service import run_chat_pipeline_trace
from backend.services.vector_service import hybrid_search
from backend.workflows.chat_workflow import run_chat_graph_workflow

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    device_model: Optional[str] = None
    image_path: Optional[str] = None
    mock_llm: bool = False
    debug: bool = False


class ChatResponse(BaseModel):
    question: str
    answer: str
    structured_answer: Optional[dict[str, Any]] = None
    contexts: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    grounding_result: dict[str, Any]
    retrieval_filter: dict[str, Any]
    graph_context: dict[str, Any] = Field(default_factory=dict)
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    seed_nodes: list[dict[str, Any]] = Field(default_factory=list)
    graph_enabled: bool = False
    graph_warnings: list[str] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    degraded: bool = False
    model_status: str = "available"
    llm_status: str = "available"
    request_id: str = ""
    workflow_backend: str = ""
    workflow_steps: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)


@router.post("")
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = run_chat_graph_workflow(
            query=request.question,
            top_k=request.top_k,
            device_model=request.device_model,
            image_path=request.image_path,
            mock_llm=request.mock_llm,
        )
        return build_chat_response(request.question, result, include_debug=request.debug)
    except Exception as exc:
        error = {"node": "run_chat_graph_workflow", "message": sanitize_error(exc)}
        print(f"[ChatGraphWorkflow] fallback to legacy chat path. reason: {exc}")
        try:
            legacy_response = run_legacy_chat(request)
        except Exception as legacy_exc:
            fallback_answer = build_degraded_answer([], {}, f"新 workflow 与 legacy 均不可用：{sanitize_error(legacy_exc)}")
            return ChatResponse(
                question=request.question,
                answer=fallback_answer,
                structured_answer=None,
                contexts=[],
                evidence_items=[],
                grounding_result=build_grounding_result([]),
                retrieval_filter={"filter_fallback": True, "filter_message": "新 workflow 与 legacy 均不可用"},
                graph_context={},
                graph_paths=[],
                seed_nodes=[],
                graph_enabled=False,
                graph_warnings=["新 workflow 与 legacy 均不可用"],
                tool_trace=[],
                degraded=True,
                model_status="unavailable",
                llm_status="unavailable",
                workflow_backend="legacy_fallback",
                errors=[error, {"node": "legacy_fallback", "message": sanitize_error(legacy_exc)}],
                debug={"workflow_error": error} if request.debug else {},
            )
        response_data = legacy_response_to_dict(legacy_response)
        response_data["degraded"] = True
        response_data["workflow_backend"] = "legacy_fallback"
        response_data["errors"] = [*response_data.get("errors", []), error]
        if request.debug:
            response_data["debug"] = {**response_data.get("debug", {}), "workflow_error": error}
        return ChatResponse(**response_data)


@router.post("/legacy")
def chat_legacy(request: ChatRequest) -> ChatResponse:
    return run_legacy_chat(request)


def build_chat_response(question: str, result: dict[str, Any], include_debug: bool = False) -> ChatResponse:
    contexts = ensure_list_of_dicts(result.get("contexts"))
    graph_context = ensure_dict(result.get("graph_context"))
    evidence_items = ensure_list_of_dicts(result.get("evidence_items")) or build_evidence_items(contexts)
    retrieval_filter = ensure_dict(result.get("retrieval_filter")) or build_retrieval_filter_result(contexts)
    grounding_result = ensure_dict(result.get("grounding_result")) or build_grounding_result(contexts)
    response_debug = ensure_dict(result.get("debug")) if include_debug else {}
    return ChatResponse(
        question=str(result.get("question") or question),
        answer=str(result.get("answer") or ""),
        structured_answer=result.get("structured_answer") if isinstance(result.get("structured_answer"), dict) else None,
        contexts=contexts,
        evidence_items=evidence_items,
        grounding_result=grounding_result,
        retrieval_filter=retrieval_filter,
        graph_context=graph_context,
        graph_paths=ensure_list_of_dicts(result.get("graph_paths")) or ensure_list_of_dicts(graph_context.get("paths")),
        seed_nodes=ensure_list_of_dicts(result.get("seed_nodes")) or ensure_list_of_dicts(graph_context.get("seed_nodes")),
        graph_enabled=bool(result.get("graph_enabled", graph_context.get("enabled", False))),
        graph_warnings=list(result.get("graph_warnings") or graph_context.get("warnings") or []),
        tool_trace=ensure_list_of_dicts(result.get("tool_trace")),
        degraded=bool(result.get("degraded", False)),
        model_status=str(result.get("model_status") or "available"),
        llm_status=str(result.get("llm_status") or result.get("model_status") or "available"),
        request_id=str(result.get("request_id") or ""),
        workflow_backend=str(result.get("workflow_backend") or ""),
        workflow_steps=ensure_list_of_dicts(result.get("workflow_steps")),
        sources=ensure_list_of_dicts(result.get("sources")),
        errors=ensure_list_of_dicts(result.get("errors")),
        debug=response_debug,
    )


def run_legacy_chat(request: ChatRequest) -> ChatResponse:
    if request.mock_llm:
        contexts = hybrid_search(request.question, top_k=request.top_k, device_model=request.device_model)
        graph_context = build_lazy_graph_context(request.question, contexts, device_model=request.device_model)
        answer = build_degraded_answer(contexts, graph_context, "mock_llm=true，legacy 入口未调用真实大模型")
        retrieval_filter = build_retrieval_filter_result(contexts)
        tool_trace = run_chat_pipeline_trace(request.question, contexts, retrieval_filter, graph_context)
        tool_trace.append(build_llm_trace(True, 0, "mock_llm=true"))
        return ChatResponse(
            question=request.question,
            answer=answer,
            structured_answer=parse_structured_answer(answer),
            contexts=contexts,
            evidence_items=build_evidence_items(contexts),
            grounding_result=build_grounding_result(contexts),
            retrieval_filter=retrieval_filter,
            graph_context=graph_context,
            graph_paths=graph_context.get("paths", []),
            seed_nodes=graph_context.get("seed_nodes", []),
            graph_enabled=bool(graph_context.get("enabled", False)),
            graph_warnings=graph_context.get("warnings", []),
            tool_trace=tool_trace,
            degraded=True,
            model_status="mocked",
            llm_status="mocked",
            workflow_backend="legacy",
        )

    try:
        result = run_langchain_chat(
            request.question,
            top_k=request.top_k,
            device_model=request.device_model,
        )
        return build_chat_response(request.question, result, include_debug=request.debug)
    except Exception as exc:
        print(f"[LangChain Pipeline] fallback to compatible chat path. reason: {exc}")

    degraded = False
    llm_status = "available"
    llm_error = ""
    llm_duration_ms = 0

    try:
        try:
            from backend.rag.rag_chain import generate_rag_answer_with_graph_info

            filters = {"device_model": request.device_model} if request.device_model else None
            answer, contexts, _filter_info, graph_context = generate_rag_answer_with_graph_info(
                request.question,
                top_k=request.top_k,
                filters=filters,
            )
        except Exception as exc:
            print(f"[LangChain RAG] fallback to legacy search. reason: {exc}")
            contexts = []
            answer = ""
            graph_context = {}

        if not contexts:
            contexts = hybrid_search(request.question, top_k=request.top_k, device_model=request.device_model)
            graph_context = build_lazy_graph_context(request.question, contexts, device_model=request.device_model)
            llm_started_at = time.perf_counter()
            try:
                answer = generate_repair_answer(request.question, contexts)
            except Exception as exc:
                llm_duration_ms = elapsed_ms(llm_started_at)
                llm_error = sanitize_error(exc)
                degraded = True
                llm_status = "unavailable"
                answer = build_degraded_answer(contexts, graph_context, llm_error)
                print(f"[Chat] LLM unavailable, return degraded answer. reason: {exc}")
            else:
                llm_duration_ms = elapsed_ms(llm_started_at)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="问答服务处理失败") from exc

    if not answer:
        degraded = True
        llm_status = "unavailable"
        llm_error = llm_error or "LLM 未返回有效回答"
        answer = build_degraded_answer(contexts, graph_context, llm_error)
    elif is_model_unavailable_answer(answer):
        degraded = True
        llm_status = "unavailable"
        llm_error = extract_model_error(answer) or "大模型服务暂时不可用"
        answer = build_degraded_answer(contexts, graph_context, llm_error)

    retrieval_filter = build_retrieval_filter_result(contexts)
    tool_trace = run_chat_pipeline_trace(request.question, contexts, retrieval_filter, graph_context)
    tool_trace.append(build_llm_trace(degraded, llm_duration_ms, llm_error))
    return ChatResponse(
        question=request.question,
        answer=answer,
        structured_answer=parse_structured_answer(answer),
        contexts=contexts,
        evidence_items=build_evidence_items(contexts),
        grounding_result=build_grounding_result(contexts),
        retrieval_filter=retrieval_filter,
        graph_context=graph_context,
        graph_paths=graph_context.get("paths", []),
        seed_nodes=graph_context.get("seed_nodes", []),
        graph_enabled=bool(graph_context.get("enabled", False)),
        graph_warnings=graph_context.get("warnings", []),
        tool_trace=tool_trace,
        degraded=degraded,
        model_status=llm_status,
        llm_status=llm_status,
        workflow_backend="legacy",
    )


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def legacy_response_to_dict(response: ChatResponse) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    return response.dict()


def parse_structured_answer(answer: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def is_model_unavailable_answer(answer: str) -> bool:
    parsed = parse_structured_answer(answer)
    if not parsed:
        return False
    text = " ".join(
        str(parsed.get(key, ""))
        for key in ("fault_summary", "fallback_notice", "evidence_strength", "manual_coverage")
    )
    return any(marker in text for marker in ("QWEN_API_KEY", "Qwen API", "大模型", "模型未返回", "无法生成 RAG 回答"))


def extract_model_error(answer: str) -> str:
    parsed = parse_structured_answer(answer)
    if not parsed:
        return ""
    return sanitize_error(Exception(str(parsed.get("fault_summary") or parsed.get("fallback_notice") or "")))


def build_degraded_answer(
    contexts: list[dict[str, Any]],
    graph_context: Optional[dict[str, Any]] = None,
    reason: str = "",
) -> str:
    lines = [
        "当前大模型服务暂时不可用，系统已根据本地知识库检索到以下参考依据。",
        "请优先查看手册页码、来源片段和现场安全要求，必要时由设备工程师复核后再执行。",
    ]
    if reason:
        lines.append(f"模型状态：{reason}")

    if contexts:
        lines.append("")
        lines.append("已检索到的参考依据：")
        for index, context in enumerate(contexts[:5], start=1):
            filename = context.get("filename") or context.get("pdf_filename") or context.get("source") or "未知来源"
            page = context.get("page_number") or context.get("page") or "未知页码"
            source_type = context.get("source_type") or context.get("doc_type") or "manual_text"
            content = " ".join(str(context.get("content") or "").split())
            snippet = content[:180] + ("..." if len(content) > 180 else "")
            lines.append(f"{index}. 来源类型：{source_type}；文件：{filename}；页码：{page}；片段：{snippet}")
    else:
        lines.append("")
        lines.append("当前本地检索也未返回可用依据，不能形成标准作业卡。")

    graph_context = graph_context or {}
    paths = graph_context.get("paths") or []
    if paths:
        lines.append("")
        lines.append("关联图谱路径：")
        for path in paths[:5]:
            lines.append(f"- {format_graph_path(path)}")

    lines.append("")
    lines.append("降级提示：当前结果不是大模型生成的完整诊断结论，请以手册原文和现场规程为准。")
    return "\n".join(lines)


def build_llm_trace(degraded: bool, duration_ms: int, error: str = "") -> dict[str, Any]:
    if degraded:
        return build_tool_result(
            "LLMGenerationTool",
            "大模型回答生成工具",
            "failed",
            input_summary="生成检修诊断回答",
            output_summary="大模型服务不可用，已返回本地检索降级结果",
            duration_ms=duration_ms,
            error=error or "LLM unavailable",
            metadata={"degraded": True, "model_status": "unavailable"},
        )
    return build_tool_result(
        "LLMGenerationTool",
        "大模型回答生成工具",
        "success",
        input_summary="生成检修诊断回答",
        output_summary="大模型回答生成完成",
        duration_ms=duration_ms,
        metadata={"degraded": False, "model_status": "available"},
    )


def sanitize_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:180] + ("..." if len(message) > 180 else "")


def format_graph_path(path: Any) -> str:
    if isinstance(path, str):
        return path
    if not isinstance(path, dict):
        return str(path)
    source = path.get("source") or path.get("from") or path.get("source_name") or ""
    relation = path.get("relation") or path.get("edge") or "related_to"
    target = path.get("target") or path.get("to") or path.get("target_name") or ""
    if source or target:
        return f"{source} --{relation}--> {target}".strip()
    return str(path)
