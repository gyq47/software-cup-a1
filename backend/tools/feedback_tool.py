from __future__ import annotations

from typing import Any, Optional

from backend.rag.metadata_service import normalize_device_model
from backend.tools.base import ToolResult, run_tool_safely, tool_skipped, tool_success


def run_feedback_case_tool(
    query: str,
    device_model: Optional[str] = None,
    limit: int = 3,
) -> ToolResult:
    def _run() -> ToolResult:
        from backend.services.feedback_service import get_cases

        requested_device = normalize_device_model(device_model)
        cases = get_cases().get("items", [])
        matched = [
            normalize_case(case)
            for case in cases
            if case_matches(case, query, requested_device)
        ][:limit]
        if not matched:
            return tool_skipped(
                name="FeedbackCaseTool",
                summary="未匹配到可用审核案例",
                data={"feedback_cases": []},
            )
        return tool_success(
            name="FeedbackCaseTool",
            summary=f"匹配审核案例 {len(matched)} 条",
            data={"feedback_cases": matched},
            sources=matched,
        )

    return run_tool_safely("FeedbackCaseTool", _run, failed_summary="反馈案例召回失败")


def case_matches(case: dict[str, Any], query: str, requested_device: str) -> bool:
    case_device = normalize_device_model(case.get("device") or case.get("related_device"))
    if requested_device and case_device and case_device not in {"common", requested_device}:
        return False
    text = " ".join(
        [
            str(case.get("title", "")),
            str(case.get("fault", "")),
            str(case.get("correction_text", "")),
            " ".join(str(item) for item in case.get("keywords", []) if item),
        ]
    ).lower()
    tokens = [token.lower() for token in query.split() if len(token.strip()) >= 2]
    return not tokens or any(token in text for token in tokens)


def normalize_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id", ""),
        "title": case.get("title", ""),
        "device_model": normalize_device_model(case.get("device") or case.get("related_device")),
        "fault": case.get("fault", ""),
        "content": case.get("correction_text", ""),
        "source_type": "feedback_case",
        "created_at": case.get("created_at", ""),
    }
