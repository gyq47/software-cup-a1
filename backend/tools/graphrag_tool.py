from __future__ import annotations

from typing import Any, Optional

from backend.tools.base import ToolResult, run_tool_safely, tool_skipped, tool_success


def run_lazy_graphrag_tool(
    query: str,
    filtered_contexts: list[dict[str, Any]],
    device_model: Optional[str] = None,
) -> ToolResult:
    def _run() -> ToolResult:
        if not query.strip() and not filtered_contexts:
            return tool_skipped(
                name="LazyGraphRAGTool",
                summary="缺少查询和检索上下文，跳过图谱增强",
                data={"graph_context": empty_graph_context("缺少查询和检索上下文")},
            )

        from backend.services.lazy_graphrag_service import build_lazy_graph_context

        graph_context = build_lazy_graph_context(query, filtered_contexts, device_model=device_model)
        enabled = bool(graph_context.get("enabled", False))
        path_count = len(graph_context.get("paths") or [])
        if not enabled:
            return tool_skipped(
                name="LazyGraphRAGTool",
                summary=(graph_context.get("warnings") or ["未匹配到可用图谱路径"])[0],
                data={"graph_context": graph_context},
            )
        return tool_success(
            name="LazyGraphRAGTool",
            summary=f"匹配图谱路径 {path_count} 条",
            data={"graph_context": graph_context},
            sources=graph_context.get("paths") or [],
        )

    return run_tool_safely("LazyGraphRAGTool", _run, failed_summary="Lazy GraphRAG 图谱增强失败")


def empty_graph_context(reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "seed_nodes": [],
        "expanded_nodes": [],
        "edges": [],
        "paths": [],
        "graph_context_text": "",
        "warnings": [reason],
    }

