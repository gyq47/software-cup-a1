#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from backend.main import app
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

        client = TestClient(app, raise_server_exceptions=False)
        response_808d = client.post(
            "/api/chat",
            json={
                "question": "808D 报警 20000 怎么处理？",
                "top_k": 5,
                "device_model": "SINUMERIK 808D",
                "mock_llm": True,
                "debug": True,
            },
        )
        response_828d = client.post(
            "/api/chat",
            json={
                "question": "828D 驱动报警如何诊断？",
                "top_k": 5,
                "device_model": "SINUMERIK 828D",
                "mock_llm": True,
                "debug": True,
            },
        )
        legacy_response = client.post(
            "/api/chat/legacy",
            json={
                "question": "808D 报警 20000 怎么处理？",
                "top_k": 3,
                "device_model": "SINUMERIK 808D",
                "mock_llm": True,
            },
        )
    finally:
        chat_workflow.run_rag_retrieval_tool = original_rag
        chat_workflow.run_lazy_graphrag_tool = original_graph
        chat_workflow.run_vision_context_tool = original_vision
        chat_workflow.run_feedback_case_tool = original_feedback

    data_808d = safe_json(response_808d)
    data_828d = safe_json(response_828d)
    legacy_data = safe_json(legacy_response)
    expected_backend = "langgraph" if is_langgraph_installed() else "sequential_fallback"

    tests = [
        {"name": "/api/chat 808D status", "passed": response_808d.status_code == 200, "status": response_808d.status_code},
        {"name": "/api/chat 828D status", "passed": response_828d.status_code == 200, "status": response_828d.status_code},
        validate_payload("808D payload", data_808d, expected_backend, forbidden="828D"),
        validate_payload("828D payload", data_828d, expected_backend, forbidden="808D"),
        validate_response_fallback_fields(data_808d),
        validate_frontend_fields(data_808d),
        validate_legacy(legacy_response.status_code, legacy_data),
    ]
    report = {
        "success": all(item["passed"] for item in tests),
        "tests": tests,
        "sample": {
            "workflow_backend": data_808d.get("workflow_backend", ""),
            "workflow_step_count": len(data_808d.get("workflow_steps", [])),
            "context_devices": [item.get("device_model") for item in data_808d.get("contexts", [])],
            "legacy_status_code": legacy_response.status_code,
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
    ]
    return tool_success(
        name="RagRetrievalTool",
        summary=f"mock 召回 {len(contexts)} 条片段",
        data={
            "raw_contexts": contexts,
            "retrieval_filter": {
                "used_device_filter": True,
                "filter_fallback": True,
                "filter_message": "mock fallback for API workflow test",
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
        "paths": [{"source": "报警", "relation": "affects", "target": "轴无法回零", "device_model": device_model}],
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

    return tool_skipped(name="FeedbackCaseTool", summary="mock 未匹配到反馈案例", data={"feedback_cases": []})


def context(chunk_id: str, device_model: str, filename: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "device_model": device_model,
        "content": f"{device_model} 维修证据 {chunk_id}",
        "filename": filename,
        "pdf_filename": filename,
        "page": 1,
        "page_number": 1,
        "source_type": "manual_text",
        "final_score": 1.0,
        "retrieval_backend": "mock",
    }


def validate_payload(name: str, data: dict[str, object], expected_backend: str, forbidden: str) -> dict[str, object]:
    contexts = data.get("contexts") if isinstance(data.get("contexts"), list) else []
    mixed = [
        item.get("device_model")
        for item in contexts
        if isinstance(item, dict) and forbidden in str(item.get("device_model", ""))
    ]
    steps = data.get("workflow_steps") if isinstance(data.get("workflow_steps"), list) else []
    passed = (
        bool(data.get("answer"))
        and isinstance(data.get("retrieval_filter"), dict)
        and bool(data.get("tool_trace"))
        and data.get("workflow_backend") == expected_backend
        and len(steps) >= 8
        and not mixed
    )
    return {
        "name": name,
        "passed": passed,
        "workflow_backend": data.get("workflow_backend", ""),
        "workflow_step_count": len(steps),
        "mixed_devices": mixed,
    }


def validate_frontend_fields(data: dict[str, object]) -> dict[str, object]:
    required = [
        "question",
        "answer",
        "structured_answer",
        "contexts",
        "evidence_items",
        "grounding_result",
        "retrieval_filter",
        "graph_context",
        "graph_paths",
        "seed_nodes",
        "graph_enabled",
        "graph_warnings",
        "tool_trace",
        "degraded",
        "model_status",
        "llm_status",
        "request_id",
        "workflow_backend",
        "workflow_steps",
        "sources",
        "errors",
        "debug",
    ]
    missing = [key for key in required if key not in data]
    return {"name": "frontend compatible fields", "passed": not missing, "missing": missing}


def validate_response_fallback_fields(data: dict[str, object]) -> dict[str, object]:
    evidence_items_ok = isinstance(data.get("evidence_items"), list)
    retrieval_filter_ok = isinstance(data.get("retrieval_filter"), dict)
    grounding_result_ok = isinstance(data.get("grounding_result"), dict)
    workflow_backend_ok = data.get("workflow_backend") == "langgraph"
    workflow_steps = data.get("workflow_steps") if isinstance(data.get("workflow_steps"), list) else []
    workflow_steps_ok = len(workflow_steps) >= 8
    contexts = data.get("contexts") if isinstance(data.get("contexts"), list) else []
    mixed_devices = [
        item.get("device_model")
        for item in contexts
        if isinstance(item, dict) and "828D" in str(item.get("device_model", ""))
    ]
    return {
        "name": "workflow response fallback fields",
        "passed": (
            evidence_items_ok
            and retrieval_filter_ok
            and grounding_result_ok
            and workflow_backend_ok
            and workflow_steps_ok
            and not mixed_devices
        ),
        "evidence_items_is_list": evidence_items_ok,
        "retrieval_filter_is_dict": retrieval_filter_ok,
        "grounding_result_is_dict": grounding_result_ok,
        "workflow_backend": data.get("workflow_backend", ""),
        "workflow_step_count": len(workflow_steps),
        "mixed_devices": mixed_devices,
    }


def validate_legacy(status_code: int, data: dict[str, object]) -> dict[str, object]:
    passed = status_code == 200 or bool(data)
    return {
        "name": "/api/chat/legacy reachable",
        "passed": passed,
        "status": status_code,
        "note": "legacy returned 200" if status_code == 200 else "legacy returned non-200 with explicit response body",
    }


def safe_json(response: object) -> dict[str, object]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def is_langgraph_installed() -> bool:
    try:
        import langgraph.graph  # noqa: F401

        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
