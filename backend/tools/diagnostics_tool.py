from __future__ import annotations

from typing import Any

from backend.tools.base import ToolResult, run_tool_safely, tool_success


def run_diagnostics_context_tool(
    query: str,
    filtered_contexts: list[dict[str, Any]],
    graph_context: dict[str, Any],
    vision_context: dict[str, Any],
) -> ToolResult:
    def _run() -> ToolResult:
        manual_count = len(filtered_contexts)
        graph_enabled = bool(graph_context.get("enabled", False))
        vision_enabled = bool(vision_context.get("enabled", False))
        confidence = build_confidence(manual_count, graph_enabled, vision_enabled)
        risk_level = detect_risk_level(query, filtered_contexts, vision_context)
        diagnostics_context = {
            "evidence_count": manual_count,
            "graph_enabled": graph_enabled,
            "vision_enabled": vision_enabled,
            "risk_level": risk_level,
            "confidence": confidence,
            "manual_coverage": "已命中维修手册依据" if manual_count else "未命中维修手册依据",
            "recommend_human_review": confidence["level"] != "high" or risk_level == "high",
        }
        return tool_success(
            name="DiagnosticsContextTool",
            summary=f"证据 {manual_count} 条，风险等级 {risk_level}，置信度 {confidence['level']}",
            data={"diagnostics_context": diagnostics_context, "confidence": confidence},
        )

    return run_tool_safely("DiagnosticsContextTool", _run, failed_summary="诊断上下文生成失败")


def build_confidence(manual_count: int, graph_enabled: bool, vision_enabled: bool) -> dict[str, Any]:
    score = min(manual_count * 0.18, 0.72)
    if graph_enabled:
        score += 0.12
    if vision_enabled:
        score += 0.08
    score = round(min(score, 0.92), 2)
    if score >= 0.72:
        level = "high"
    elif score >= 0.35:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "score": score}


def detect_risk_level(query: str, contexts: list[dict[str, Any]], vision_context: dict[str, Any]) -> str:
    text = " ".join([query, " ".join(str(item.get("content", "")) for item in contexts[:3])]).lower()
    if any(keyword in text for keyword in ("急停", "过热", "冒烟", "高压", "短路", "安全", "驱动报警")):
        return "high"
    result = vision_context.get("result") if isinstance(vision_context.get("result"), dict) else {}
    if str(result.get("risk_level", "")).lower() == "high":
        return "high"
    if any(keyword in text for keyword in ("报警", "无法", "故障", "异常")):
        return "medium"
    return "low"

