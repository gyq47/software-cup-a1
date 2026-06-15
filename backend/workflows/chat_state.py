from __future__ import annotations

from typing import Any, TypedDict


class ToolResult(TypedDict, total=False):
    name: str
    status: str
    summary: str
    data: dict[str, Any]
    sources: list[dict[str, Any]]
    duration_ms: int
    error: str | None


class ChatState(TypedDict, total=False):
    request_id: str
    query: str
    device_model: str
    alarm_code: str
    image_path: str
    query_info: dict[str, Any]
    retrieval_filter: dict[str, Any]
    raw_contexts: list[dict[str, Any]]
    filtered_contexts: list[dict[str, Any]]
    graph_context: dict[str, Any]
    vision_context: dict[str, Any]
    diagnostics_context: dict[str, Any]
    feedback_cases: list[dict[str, Any]]
    tool_results: list[ToolResult]
    tool_trace: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    answer_plan: dict[str, Any]
    final_answer: str
    confidence: dict[str, Any] | str
    degraded: bool
    errors: list[dict[str, Any]]
    timings: dict[str, int]
    debug: dict[str, Any]
    response: dict[str, Any]
    workflow_backend: str
    workflow_steps: list[dict[str, Any]]
