from __future__ import annotations

from typing import Any, Optional

from backend.rag.metadata_service import normalize_device_model
from backend.tools.base import ToolResult, run_tool_safely, tool_success


def run_rag_retrieval_tool(
    query: str,
    query_info: dict[str, Any],
    top_k: int = 5,
) -> ToolResult:
    def _run() -> ToolResult:
        from backend.rag.langchain_pipeline import detect_retrieval_backend
        from backend.rag.langchain_pipeline import exact_match_contexts
        from backend.rag.langchain_pipeline import merge_and_rank_contexts
        from backend.rag.rag_chain import generate_rag_contexts_with_info

        device_model = str(query_info.get("device_model") or "")
        filters = {"device_model": device_model} if device_model else None
        contexts, retrieval_filter = generate_rag_contexts_with_info(query, top_k=top_k, filters=filters)
        exact_contexts = exact_match_contexts(query, query_info, limit=max(top_k * 2, 10))
        contexts = merge_and_rank_contexts(contexts, exact_contexts, query_info, top_k)
        retrieval_filter = {
            **retrieval_filter,
            "used_device_filter": bool(device_model),
            "requested_device_model": device_model,
            "retrieval_backend": detect_retrieval_backend(contexts),
        }
        for context in contexts:
            context["retrieval_backend"] = context.get("retrieval_backend") or "langchain_chroma"
            context["used_device_filter"] = bool(device_model)
            context["requested_device_model"] = device_model
            context["filter_fallback"] = bool(context.get("filter_fallback", retrieval_filter.get("filter_fallback", False)))
            context["filter_message"] = context.get("filter_message") or retrieval_filter.get("filter_message", "")
        return tool_success(
            name="RagRetrievalTool",
            summary=f"召回 {len(contexts)} 条原始检索片段",
            data={
                "raw_contexts": contexts,
                "retrieval_filter": retrieval_filter,
            },
            sources=contexts,
        )

    return run_tool_safely("RagRetrievalTool", _run, failed_summary="RAG 检索失败")


def apply_device_gate_tool(
    contexts: list[dict[str, Any]],
    device_model: Optional[str],
    retrieval_filter: Optional[dict[str, Any]] = None,
) -> ToolResult:
    def _run() -> ToolResult:
        retrieval_filter_value = dict(retrieval_filter or {})
        filtered_contexts, gate_info = apply_device_gate(contexts, device_model)
        retrieval_filter_value.update(gate_info)
        retrieval_filter_value["used_device_filter"] = bool(device_model)
        retrieval_filter_value["requested_device_model"] = device_model or retrieval_filter_value.get("requested_device_model", "")
        retrieval_filter_value["filter_message"] = build_filter_message(
            str(device_model or ""),
            str(retrieval_filter_value.get("filter_message") or ""),
            bool(retrieval_filter_value.get("filter_fallback", False)),
            gate_info,
        )
        for context in filtered_contexts:
            context["used_device_filter"] = bool(device_model)
            context["requested_device_model"] = retrieval_filter_value["requested_device_model"]
            context["filter_fallback"] = bool(retrieval_filter_value.get("filter_fallback", False))
            context["filter_message"] = retrieval_filter_value.get("filter_message", "")

        dropped = int(gate_info.get("device_gate_dropped_count") or 0)
        return tool_success(
            name="DeviceGateTool",
            summary=f"保留 {len(filtered_contexts)} 条片段，过滤 {dropped} 条非目标设备片段",
            data={
                "filtered_contexts": filtered_contexts,
                "retrieval_filter": retrieval_filter_value,
            },
            sources=filtered_contexts,
        )

    return run_tool_safely("DeviceGateTool", _run, failed_summary="设备型号过滤失败")


def apply_device_gate(
    contexts: list[dict[str, Any]],
    requested_device_model: Optional[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested = normalize_device_model(requested_device_model)
    if not requested:
        return contexts, {
            "device_gate_applied": False,
            "device_gate_dropped_count": 0,
            "device_gate_dropped_devices": [],
        }

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for context in contexts:
        current = normalize_device_model(context.get("device_model"))
        if not current or is_common_device_model(current) or current == requested:
            kept.append(context)
        else:
            dropped.append(context)

    dropped_devices = sorted(
        {
            normalize_device_model(context.get("device_model")) or str(context.get("device_model") or "")
            for context in dropped
            if str(context.get("device_model") or "").strip()
        }
    )
    return kept, {
        "device_gate_applied": True,
        "device_gate_dropped_count": len(dropped),
        "device_gate_dropped_devices": dropped_devices,
    }


def is_common_device_model(device_model: str) -> bool:
    return str(device_model or "").strip().lower() in {"common", "general", "通用", "通用知识", "通用设备"}


def build_filter_message(
    device_model: str,
    existing_message: str,
    filter_fallback: bool,
    gate_info: dict[str, Any],
) -> str:
    if not device_model:
        return existing_message
    parts: list[str] = []
    if existing_message:
        parts.append(existing_message)
    elif filter_fallback:
        parts.append("当前设备型号下依据不足，已扩展检索范围")
    else:
        parts.append(f"已优先使用设备型号 {device_model} 的知识来源")

    dropped_count = int(gate_info.get("device_gate_dropped_count") or 0)
    if dropped_count:
        dropped_devices = ", ".join(gate_info.get("device_gate_dropped_devices") or [])
        message = f"device gate 已过滤 {dropped_count} 条非目标设备片段"
        if dropped_devices:
            message += f"：{dropped_devices}"
        parts.append(message)
    return "；".join(parts)
