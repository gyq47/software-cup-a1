import base64
import json
import re
from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_VL_MODEL

DEFAULT_VISION_RESULT = {
    "scene": "图像信息不足",
    "possible_faults": [],
    "visible_parts": [],
    "fault_codes": [],
    "device_model": "",
    "risk_level": "medium",
    "analysis_text": "图像信息不足，建议结合现场设备型号、报警代码和维修手册人工复核。",
}


def analyze_fault_image(
    image_bytes: bytes,
    content_type: str,
    text: str | None = None,
    device_model: str | None = None,
) -> dict[str, Any]:
    if not QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY 未配置")

    client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    image_url = build_data_url(image_bytes, content_type)

    try:
        response = client.chat.completions.create(
            model=QWEN_VL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": build_vision_system_prompt(),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": build_vision_user_prompt(text, device_model),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        raise RuntimeError("Qwen-VL API 调用失败") from exc

    content = response.choices[0].message.content
    if not content:
        return dict(DEFAULT_VISION_RESULT)

    return normalize_vision_result(parse_json_object(content))


def build_data_url(image_bytes: bytes, content_type: str) -> str:
    mime_type = content_type or "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def build_vision_system_prompt() -> str:
    return (
        "你是工业设备故障图片诊断专家，面向设备检修、故障排查和维修作业。"
        "只输出合法 JSON，不要 Markdown，不要聊天式寒暄。"
        "重点识别漏油、裂纹、烧蚀、松动、磨损、故障代码、仪表盘报警、零件名称、设备型号铭牌。"
        "如果图像无法判断，字段中明确写“图像信息不足”。"
        "risk_level 只能是 low、medium、high。"
    )


def build_vision_user_prompt(text: str | None, device_model: str | None) -> str:
    return (
        f"用户补充描述：{text or '无'}\n"
        f"用户填写设备型号：{device_model or '无'}\n"
        "请按以下 JSON 字段输出："
        "{"
        '"scene":"...",'
        '"possible_faults":["..."],'
        '"visible_parts":["..."],'
        '"fault_codes":["..."],'
        '"device_model":"...",'
        '"risk_level":"low/medium/high",'
        '"analysis_text":"..."'
        "}"
    )


def parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        stripped = fenced_match.group(1).strip()
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            stripped = stripped[start : end + 1]

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return dict(DEFAULT_VISION_RESULT)

    return parsed if isinstance(parsed, dict) else dict(DEFAULT_VISION_RESULT)


def normalize_vision_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(DEFAULT_VISION_RESULT)
    normalized.update(
        {
            "scene": normalize_text(result.get("scene"), DEFAULT_VISION_RESULT["scene"]),
            "possible_faults": normalize_string_list(result.get("possible_faults")),
            "visible_parts": normalize_string_list(result.get("visible_parts")),
            "fault_codes": normalize_string_list(result.get("fault_codes")),
            "device_model": normalize_text(result.get("device_model"), ""),
            "risk_level": normalize_risk_level(result.get("risk_level")),
            "analysis_text": normalize_text(result.get("analysis_text"), DEFAULT_VISION_RESULT["analysis_text"]),
        }
    )
    return normalized


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip() and value != "图像信息不足":
        return [value.strip()]
    return []


def normalize_text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def normalize_risk_level(value: Any) -> str:
    level = str(value or "").lower()
    return level if level in {"low", "medium", "high"} else "medium"
