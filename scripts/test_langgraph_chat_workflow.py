#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from backend.workflows import chat_workflow

    original_rag = chat_workflow.run_rag_retrieval_tool
    original_graph = chat_workflow.run_lazy_graphrag_tool
    original_vision = chat_workflow.run_vision_context_tool
    original_feedback = chat_workflow.run_feedback_case_tool

    try:
        chat_workflow.run_rag_retrieval_tool = fake_rag_tool
        chat_workflow.run_lazy_graphrag_tool = fake_graph_tool
        chat_workflow.run_vision_context_tool = fake_vision_tool
        chat_workflow.run_feedback_case_tool = fake_feedback_tool

        response_808d = chat_workflow.run_chat_graph_workflow(
            "808D 报警 20000 怎么处理？",
            top_k=5,
            device_model="SINUMERIK 808D",
            mock_llm=True,
        )
        response_828d = chat_workflow.run_chat_graph_workflow(
            "828D 驱动报警如何诊断？",
            top_k=5,
            device_model="SINUMERIK 828D",
            mock_llm=True,
        )
    finally:
        chat_workflow.run_rag_retrieval_tool = original_rag
        chat_workflow.run_lazy_graphrag_tool = original_graph
        chat_workflow.run_vision_context_tool = original_vision
        chat_workflow.run_feedback_case_tool = original_feedback

    tests = [
        validate_response("808D workflow", response_808d, "SINUMERIK 808D", forbidden="828D"),
        validate_response("828D workflow", response_828d, "SINUMERIK 828D", forbidden="808D"),
        validate_workflow_backend(response_808d),
        validate_workflow_steps(response_808d),
        {
            "name": "vision skipped",
            "passed": any(
                item.get("tool_name") == "VisionAnalysisTool" and item.get("status") == "skipped"
                for item in response_808d.get("tool_trace", [])
            ),
        },
        {
            "name": "fallback visible",
            "passed": bool(response_808d.get("retrieval_filter", {}).get("filter_fallback", False)),
        },
        {
            "name": "frontend compatible fields",
            "passed": all(
                key in response_808d
                for key in (
                    "answer",
                    "contexts",
                    "retrieval_filter",
                    "graph_context",
                    "graph_enabled",
                    "graph_warnings",
                    "tool_trace",
                    "sources",
                    "degraded",
                    "errors",
                    "request_id",
                    "workflow_steps",
                    "workflow_backend",
                )
            ),
        },
        {
            "name": "mock llm answer",
            "passed": "测试模式未调用真实大模型" in response_808d.get("answer", ""),
        },
    ]
    report = {
        "success": all(item["passed"] for item in tests),
        "tests": tests,
        "sample": {
            "workflow_backend": response_808d.get("workflow_backend", ""),
            "answer_preview": response_808d.get("answer", "")[:160],
            "tool_trace_count": len(response_808d.get("tool_trace", [])),
            "workflow_step_count": len(response_808d.get("workflow_steps", [])),
            "workflow_step_names": [item.get("name") for item in response_808d.get("workflow_steps", [])],
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


def fake_rag_tool(query: str, query_info: dict[str, object], top_k: int = 5) -> dict[str, object]:
    from backend.tools.base import tool_success

    contexts = [
        context("808d-1", "SINUMERIK 808D", "西门子SINUMERIK808D 诊断手册.pdf"),
        context("828d-1", "SINUMERIK 828D", "SINUMERIK 828D 报警诊断手册.pdf"),
        context("common-1", "common", "通用安全规程.pdf"),
        context("empty-1", "", "未标注设备资料.pdf"),
    ]
    return tool_success(
        name="RagRetrievalTool",
        summary=f"mock 召回 {len(contexts)} 条片段",
        data={
            "raw_contexts": contexts,
            "retrieval_filter": {
                "used_device_filter": True,
                "filter_fallback": True,
                "filter_message": "mock fallback for workflow test",
                "requested_device_model": query_info.get("device_model", ""),
                "retrieval_backend": "mock",
            },
        },
        sources=contexts,
    )


def fake_graph_tool(query: str, filtered_contexts: list[dict[str, object]], device_model: str = "") -> dict[str, object]:
    from backend.tools.base import tool_success

    graph_context = {
        "enabled": True,
        "seed_nodes": [{"id": "fault_axis_ref", "name": "轴无法回零"}],
        "expanded_nodes": [],
        "edges": [],
        "paths": [
            {
                "source": "报警",
                "relation": "affects",
                "target": "轴无法回零",
                "device_model": device_model,
            }
        ],
        "graph_context_text": "【关联知识图谱】\n- 报警 --affects--> 轴无法回零",
        "warnings": [],
    }
    return tool_success(
        name="LazyGraphRAGTool",
        summary="mock 图谱路径 1 条",
        data={"graph_context": graph_context},
        sources=graph_context["paths"],
    )


def fake_vision_tool(image_path: str, query: str, device_model: str = "") -> dict[str, object]:
    from backend.tools.base import tool_skipped

    return tool_skipped(
        name="VisionAnalysisTool",
        summary="未提供图片，跳过视觉上下文",
        data={"vision_context": {"enabled": False, "skipped": True, "reason": "no_image"}},
    )


def fake_feedback_tool(query: str, device_model: str = "", limit: int = 3) -> dict[str, object]:
    from backend.tools.base import tool_skipped

    return tool_skipped(
        name="FeedbackCaseTool",
        summary="mock 未匹配到反馈案例",
        data={"feedback_cases": []},
    )


def context(chunk_id: str, device_model: str, filename: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "device_model": device_model,
        "content": f"{device_model or '未标注'} 维修证据 {chunk_id}",
        "filename": filename,
        "pdf_filename": filename,
        "page": 1,
        "page_number": 1,
        "source_type": "manual_text",
        "final_score": 1.0,
        "retrieval_backend": "mock",
    }


def validate_response(name: str, response: dict[str, object], requested: str, forbidden: str) -> dict[str, object]:
    contexts = response.get("contexts") if isinstance(response.get("contexts"), list) else []
    mixed = [
        item.get("device_model")
        for item in contexts
        if isinstance(item, dict) and forbidden in str(item.get("device_model", ""))
    ]
    allowed_common = any(str(item.get("device_model", "")).lower() == "common" for item in contexts if isinstance(item, dict))
    passed = (
        bool(response.get("answer"))
        and not mixed
        and allowed_common
        and any(requested in str(item.get("device_model", "")) for item in contexts if isinstance(item, dict))
        and bool(response.get("tool_trace"))
    )
    return {
        "name": name,
        "passed": passed,
        "context_devices": [item.get("device_model") for item in contexts if isinstance(item, dict)],
        "mixed_devices": mixed,
    }


def validate_workflow_backend(response: dict[str, object]) -> dict[str, object]:
    expected = "langgraph" if is_langgraph_installed() else "sequential_fallback"
    actual = response.get("workflow_backend", "")
    return {
        "name": "workflow backend",
        "passed": actual == expected,
        "expected": expected,
        "actual": actual,
    }


def validate_workflow_steps(response: dict[str, object]) -> dict[str, object]:
    steps = response.get("workflow_steps") if isinstance(response.get("workflow_steps"), list) else []
    names = [step.get("name") for step in steps if isinstance(step, dict)]
    required = [
        "normalize_input",
        "parse_query",
        "retrieve_context",
        "device_gate",
        "lazy_graphrag",
        "vision_context",
        "diagnostics_context",
        "feedback_case",
        "plan_answer",
        "generate_answer",
        "format_sources",
        "build_tool_trace",
        "format_response",
    ]
    missing = [name for name in required if name not in names]
    shaped = all(
        isinstance(step, dict)
        and {"name", "status", "duration_ms", "summary", "degraded"}.issubset(step)
        for step in steps
    )
    return {
        "name": "workflow steps observable",
        "passed": len(steps) >= 8 and not missing and shaped,
        "workflow_step_count": len(steps),
        "missing": missing,
        "shaped": shaped,
    }


def is_langgraph_installed() -> bool:
    try:
        import langgraph.graph  # noqa: F401

        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
