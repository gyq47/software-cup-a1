from __future__ import annotations

import time
from typing import Any, Callable, Optional, TypedDict


class ToolResult(TypedDict, total=False):
    name: str
    status: str
    summary: str
    data: dict[str, Any]
    sources: list[dict[str, Any]]
    duration_ms: int
    error: Optional[str]


def elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def tool_success(
    name: str,
    summary: str,
    data: Optional[dict[str, Any]] = None,
    sources: Optional[list[dict[str, Any]]] = None,
    duration_ms: int = 0,
) -> ToolResult:
    return {
        "name": name,
        "status": "success",
        "summary": summary,
        "data": data or {},
        "sources": sources or [],
        "duration_ms": duration_ms,
        "error": None,
    }


def tool_failed(
    name: str,
    summary: str,
    error: str,
    data: Optional[dict[str, Any]] = None,
    sources: Optional[list[dict[str, Any]]] = None,
    duration_ms: int = 0,
) -> ToolResult:
    return {
        "name": name,
        "status": "failed",
        "summary": summary,
        "data": data or {},
        "sources": sources or [],
        "duration_ms": duration_ms,
        "error": error,
    }


def tool_skipped(
    name: str,
    summary: str,
    data: Optional[dict[str, Any]] = None,
    sources: Optional[list[dict[str, Any]]] = None,
    duration_ms: int = 0,
) -> ToolResult:
    return {
        "name": name,
        "status": "skipped",
        "summary": summary,
        "data": data or {},
        "sources": sources or [],
        "duration_ms": duration_ms,
        "error": None,
    }


def run_tool_safely(
    name: str,
    function: Callable[[], ToolResult],
    failed_summary: str = "工具执行失败",
) -> ToolResult:
    started_at = time.perf_counter()
    try:
        result = function()
        result["duration_ms"] = result.get("duration_ms", 0) or elapsed_ms(started_at)
        return result
    except Exception as exc:
        return tool_failed(
            name=name,
            summary=failed_summary,
            error=sanitize_error(exc),
            duration_ms=elapsed_ms(started_at),
        )


def sanitize_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:240] + ("..." if len(message) > 240 else "")
