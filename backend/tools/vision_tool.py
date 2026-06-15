from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from backend.tools.base import ToolResult, run_tool_safely, tool_skipped, tool_success


def run_vision_context_tool(
    image_path: Optional[str],
    query: str,
    device_model: Optional[str] = None,
) -> ToolResult:
    def _run() -> ToolResult:
        if not image_path:
            return tool_skipped(
                name="VisionAnalysisTool",
                summary="未提供图片，跳过视觉上下文",
                data={"vision_context": {"enabled": False, "skipped": True, "reason": "no_image"}},
            )

        path = Path(image_path)
        if not path.exists() or not path.is_file():
            return tool_skipped(
                name="VisionAnalysisTool",
                summary="图片文件不存在，跳过视觉上下文",
                data={"vision_context": {"enabled": False, "skipped": True, "reason": "image_not_found"}},
            )

        from backend.services.vision_service import analyze_fault_image

        image_bytes = path.read_bytes()
        vision_result = analyze_fault_image(
            image_bytes=image_bytes,
            content_type=guess_content_type(path),
            text=query,
            device_model=device_model,
        )
        return tool_success(
            name="VisionAnalysisTool",
            summary="已生成视觉分析上下文",
            data={"vision_context": {"enabled": True, "result": vision_result}},
        )

    return run_tool_safely("VisionAnalysisTool", _run, failed_summary="视觉分析失败")


def guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"

