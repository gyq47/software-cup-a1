import json
import re
from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.services.context_cleaner import clean_contexts
from backend.services.vector_service import hybrid_search
from backend.services.vision_service import analyze_fault_image

DEFAULT_DIAGNOSIS = {
    "summary": "知识库依据不足，建议人工复核。",
    "fault_analysis": [],
    "inspection_steps": [],
    "repair_suggestions": [],
    "safety_notices": ["停机断电后检查，必要时由专业人员处理。"],
    "risk_level": "medium",
    "generated_query": "",
    "workflow_recommended": True,
}


def diagnose_fault_image(
    image_bytes: bytes,
    content_type: str,
    text: str | None = None,
    device_model: str | None = None,
) -> dict[str, Any]:
    vision_result = analyze_fault_image(
        image_bytes=image_bytes,
        content_type=content_type,
        text=text,
        device_model=device_model,
    )
    generated_query = build_multimodal_query(text, device_model, vision_result)
    contexts = hybrid_search(generated_query, top_k=5) if generated_query else []
    cleaned_contexts = clean_contexts(generated_query or text or "", contexts)
    diagnosis = generate_diagnosis_report(
        generated_query=generated_query,
        vision_result=vision_result,
        contexts=cleaned_contexts,
    )
    diagnosis["generated_query"] = generated_query

    return {
        "vision_result": vision_result,
        "diagnosis": diagnosis,
        "contexts": contexts,
    }


def build_multimodal_query(
    text: str | None,
    device_model: str | None,
    vision_result: dict[str, Any],
) -> str:
    parts: list[str] = []
    parts.extend([text or "", device_model or ""])
    parts.append(str(vision_result.get("device_model", "")))
    parts.append(str(vision_result.get("scene", "")))
    parts.extend(to_string_list(vision_result.get("visible_parts", [])))
    parts.extend(to_string_list(vision_result.get("possible_faults", [])))
    parts.extend(to_string_list(vision_result.get("fault_codes", [])))
    parts.append(str(vision_result.get("analysis_text", "")))

    seen: set[str] = set()
    keywords: list[str] = []
    for part in parts:
        for token in extract_query_tokens(part):
            if token not in seen and token != "图像信息不足":
                seen.add(token)
                keywords.append(token)
    return " ".join(keywords)


def generate_diagnosis_report(
    generated_query: str,
    vision_result: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY 未配置")

    client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    try:
        response = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": build_diagnosis_system_prompt(),
                },
                {
                    "role": "user",
                    "content": build_diagnosis_user_prompt(generated_query, vision_result, contexts),
                },
            ],
            temperature=0.15,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        raise RuntimeError("Qwen 诊断生成调用失败") from exc

    content = response.choices[0].message.content
    if not content:
        return dict(DEFAULT_DIAGNOSIS)

    parsed = parse_json_object(content)
    return normalize_diagnosis(parsed, vision_result)


def build_diagnosis_system_prompt() -> str:
    return (
        "你是工业设备故障诊断专家，输出必须像维修诊断报告，不要聊天语气。"
        "必须结合图片识别结果和知识库片段，偏故障诊断、专家辅助、可解释。"
        "不要输出 Markdown，只输出合法 JSON。"
        "如果知识库依据不足，必须在 summary 或建议中写“建议人工复核”。"
        "JSON 字段必须包含 summary、fault_analysis、inspection_steps、repair_suggestions、"
        "safety_notices、risk_level、workflow_recommended。risk_level 只能是 low、medium、high。"
    )


def build_diagnosis_user_prompt(
    generated_query: str,
    vision_result: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> str:
    return (
        f"自动生成检索 query：{generated_query}\n\n"
        f"图片识别结果：\n{json.dumps(vision_result, ensure_ascii=False)}\n\n"
        f"知识库片段：\n{format_contexts(contexts)}\n\n"
        "请输出 JSON："
        "{"
        '"summary":"...",'
        '"fault_analysis":["..."],'
        '"inspection_steps":["..."],'
        '"repair_suggestions":["..."],'
        '"safety_notices":["..."],'
        '"risk_level":"low/medium/high",'
        '"workflow_recommended":true'
        "}"
    )


def format_contexts(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return "知识库依据不足，建议人工复核。"

    formatted: list[str] = []
    for index, context in enumerate(contexts, start=1):
        formatted.append(
            f"[{index}] 文件：{context.get('filename', '未知文件')}；页码：{context.get('page', '未知')}；"
            f"chunk_id：{context.get('chunk_id', '')}；final_score：{context.get('final_score', 0)}\n"
            f"{context.get('content', '')}"
        )
    return "\n\n".join(formatted)


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
        return dict(DEFAULT_DIAGNOSIS)
    return parsed if isinstance(parsed, dict) else dict(DEFAULT_DIAGNOSIS)


def normalize_diagnosis(result: dict[str, Any], vision_result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(DEFAULT_DIAGNOSIS)
    normalized.update(
        {
            "summary": normalize_text(result.get("summary"), DEFAULT_DIAGNOSIS["summary"]),
            "fault_analysis": to_string_list(result.get("fault_analysis")),
            "inspection_steps": to_string_list(result.get("inspection_steps")),
            "repair_suggestions": to_string_list(result.get("repair_suggestions")),
            "safety_notices": to_string_list(result.get("safety_notices")),
            "risk_level": normalize_risk_level(result.get("risk_level") or vision_result.get("risk_level")),
            "workflow_recommended": bool(result.get("workflow_recommended", True)),
        }
    )
    return normalized


def extract_query_tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_/-]{2,}", str(text).lower())


def to_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def normalize_risk_level(value: Any) -> str:
    level = str(value or "").lower()
    return level if level in {"low", "medium", "high"} else "medium"
