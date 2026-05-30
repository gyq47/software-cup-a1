import base64
import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from backend.core.config import (
    DISABLE_IMAGE_KNOWLEDGE,
    IMAGE_KNOWLEDGE_MAX_PAGES,
    IMAGE_KNOWLEDGE_PATH,
    IMAGE_KNOWLEDGE_QWEN_TIMEOUT,
    IMAGE_KNOWLEDGE_VL_MODE,
    MANUAL_PAGE_IMAGE_PATH,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_VL_MODEL,
)

IMAGE_KNOWLEDGE_FAST_PROMPT = (
    "请用不超过120字概括这张工业维修手册页面的主要内容，并提取5个以内关键词。"
    "只返回JSON：{\"summary\":\"...\",\"keywords\":[\"...\"]}"
)
IMAGE_KNOWLEDGE_DETAILED_PROMPT = (
    "你是一名工业设备检修专家。请分析这张维修手册页面截图中的图像知识。"
    "重点识别：报警界面、参数界面、PLC信号图、接线图、电气原理图、流程图、操作步骤图、维修示意图、设备结构图、故障诊断图。"
    "不要编造图片中不存在的信息。只输出合法 JSON，不要 Markdown。"
    "JSON 格式：{\"summary\":\"...\",\"keywords\":[\"...\"],\"objects\":[\"...\"]}。"
    "如果图片信息不足，summary 写“图像信息不足”，keywords 和 objects 返回空数组。"
)
MAX_OCR_CHARS = 2000
MAX_SUMMARY_CHARS = 1200
MAX_KEYWORDS = 12


def extract_page_image_knowledge(
    image_path: str | Path,
    device_model: str,
    manual_type: str,
    pdf_filename: str,
    page_number: int,
) -> dict[str, Any]:
    if DISABLE_IMAGE_KNOWLEDGE:
        return {
            "ocr_text": "",
            "image_summary": "",
            "keywords": [],
            "objects": [],
            "document_content": "",
            "device_model": device_model,
            "manual_type": manual_type,
            "pdf_filename": pdf_filename,
            "page_number": page_number,
        }

    path = Path(image_path)
    cached = load_cached_knowledge(path)
    if cached is not None:
        return cached

    ocr_text = run_optional_ocr(path)
    vision_result = analyze_manual_page_image(path)
    image_summary = str(vision_result.get("summary") or "")
    keywords = merge_keywords(
        vision_result.get("keywords"),
        ocr_text,
        image_summary,
        str(vision_result.get("objects") or ""),
    )
    payload = {
        "ocr_text": truncate_text(ocr_text, MAX_OCR_CHARS),
        "image_summary": truncate_text(image_summary, MAX_SUMMARY_CHARS),
        "keywords": keywords,
        "objects": normalize_string_list(vision_result.get("objects")),
        "document_content": build_document_content(
            pdf_filename=pdf_filename,
            page_number=page_number,
            ocr_text=ocr_text,
            image_summary=image_summary,
            keywords=keywords,
        ),
        "device_model": device_model,
        "manual_type": manual_type,
        "pdf_filename": pdf_filename,
        "page_number": page_number,
    }
    if has_useful_knowledge(payload):
        save_cached_knowledge(path, payload)
    return payload


def build_page_image_documents(
    file_path: str | Path,
    document_metadata: dict[str, Any],
    page_images: dict[int, str],
    max_pages: int | None = None,
) -> list[Any]:
    if DISABLE_IMAGE_KNOWLEDGE:
        print("[PDF Image Knowledge] disabled, skip manual image knowledge.")
        return []

    if not page_images:
        return []

    from langchain_core.documents import Document

    path = Path(file_path)
    documents: list[Any] = []
    page_limit = IMAGE_KNOWLEDGE_MAX_PAGES if max_pages is None else max(max_pages, 0)
    if page_limit <= 0:
        return []

    processed_pages = 0
    for page_number, relative_image_path in sorted(page_images.items()):
        if processed_pages >= page_limit:
            break
        processed_pages += 1
        image_path = resolve_project_path(relative_image_path)
        knowledge = extract_page_image_knowledge(
            image_path=image_path,
            device_model=str(document_metadata.get("device_model", "")),
            manual_type=str(document_metadata.get("manual_type", "")),
            pdf_filename=path.name,
            page_number=page_number,
        )
        if not has_useful_knowledge(knowledge):
            continue

        metadata = {
            **document_metadata,
            "source_type": "manual_image",
            "doc_type": "image_knowledge",
            "filename": path.name,
            "pdf_filename": path.name,
            "page": page_number,
            "page_number": page_number,
            "page_image_path": relative_image_path,
            "chunk_id": f"{path.name}-image-p{page_number}",
            "image_keywords": ", ".join(knowledge.get("keywords", [])),
        }
        documents.append(Document(page_content=knowledge["document_content"], metadata=metadata))
    return documents


def run_optional_ocr(image_path: Path) -> str:
    try:
        import pytesseract

        text = pytesseract.image_to_string(str(image_path), lang="chi_sim+eng", timeout=8)
        return normalize_whitespace(text)
    except Exception as exc:
        print(f"[PDF Image Knowledge] OCR unavailable for {image_path.name}. reason: {exc}")
        return ""


def analyze_manual_page_image(image_path: Path) -> dict[str, Any]:
    if DISABLE_IMAGE_KNOWLEDGE:
        return {"summary": "", "keywords": [], "objects": []}

    if not QWEN_API_KEY:
        return {"summary": "", "keywords": [], "objects": []}

    try:
        client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, timeout=IMAGE_KNOWLEDGE_QWEN_TIMEOUT)
        request_payload = {
            "model": QWEN_VL_MODEL,
            "messages": [
                {"role": "system", "content": build_image_knowledge_prompt()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_image_knowledge_user_prompt()},
                        {"type": "image_url", "image_url": {"url": build_image_data_url(image_path)}},
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": 120 if IMAGE_KNOWLEDGE_VL_MODE != "detailed" else 256,
        }
        if IMAGE_KNOWLEDGE_VL_MODE == "detailed":
            request_payload["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**request_payload)
        content = response.choices[0].message.content or "{}"
        return normalize_vision_json(parse_json_object(content))
    except Exception as exc:
        print(f"[PDF Image Knowledge] Qwen-VL skipped for {image_path.name}. reason: {exc}")
        return {"summary": "", "keywords": [], "objects": []}


def build_image_knowledge_prompt() -> str:
    if IMAGE_KNOWLEDGE_VL_MODE == "detailed":
        return IMAGE_KNOWLEDGE_DETAILED_PROMPT
    return IMAGE_KNOWLEDGE_FAST_PROMPT


def build_image_knowledge_user_prompt() -> str:
    if IMAGE_KNOWLEDGE_VL_MODE == "detailed":
        return "请将该维修手册页面截图转化为可检索的图像知识。"
    return "概括这张维修手册页面并提取关键词。"


def build_document_content(
    pdf_filename: str,
    page_number: int,
    ocr_text: str,
    image_summary: str,
    keywords: list[str],
) -> str:
    return "\n".join(
        [
            "【图片知识】",
            f"文件：{pdf_filename}",
            f"页码：{page_number}",
            f"OCR内容：{truncate_text(ocr_text, MAX_OCR_CHARS) or '未识别到文字'}",
            f"图像分析：{truncate_text(image_summary, MAX_SUMMARY_CHARS) or '图像信息不足'}",
            f"关键词：{'、'.join(keywords) if keywords else '无'}",
        ]
    )


def build_image_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    mime_type = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


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
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_vision_json(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": str(payload.get("summary") or "").strip(),
        "keywords": normalize_string_list(payload.get("keywords")),
        "objects": normalize_string_list(payload.get("objects")),
    }


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:MAX_KEYWORDS]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def merge_keywords(*values: Any) -> list[str]:
    keywords: list[str] = []
    for value in values:
        if isinstance(value, list):
            candidates = [str(item) for item in value]
        else:
            candidates = re.findall(r"[A-Za-z]+\d*|\d+[A-Za-z]*|[\u4e00-\u9fff]{2,}", str(value or ""))
        for candidate in candidates:
            normalized = candidate.strip()
            if len(normalized) < 2 or normalized in keywords or normalized == "图像信息不足":
                continue
            keywords.append(normalized)
            if len(keywords) >= MAX_KEYWORDS:
                return keywords
    return keywords


def has_useful_knowledge(knowledge: dict[str, Any]) -> bool:
    ocr_text = str(knowledge.get("ocr_text", "")).strip()
    image_summary = str(knowledge.get("image_summary", "")).strip()
    keywords = [item for item in knowledge.get("keywords", []) if item and item != "图像信息不足"]
    if image_summary == "图像信息不足":
        image_summary = ""
    return bool(ocr_text or image_summary or keywords)


def load_cached_knowledge(image_path: Path) -> dict[str, Any] | None:
    cache_path = build_cache_path(image_path)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def save_cached_knowledge(image_path: Path, payload: dict[str, Any]) -> None:
    cache_path = build_cache_path(image_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_cache_path(image_path: Path) -> Path:
    try:
        relative = image_path.resolve().relative_to(MANUAL_PAGE_IMAGE_PATH.resolve())
    except ValueError:
        relative = Path(image_path.name)
    return (IMAGE_KNOWLEDGE_PATH / relative).with_suffix(".json")


def resolve_project_path(path: str | Path) -> Path:
    raw_path = Path(path)
    return raw_path if raw_path.is_absolute() else Path.cwd() / raw_path


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate_text(text: str, max_chars: int) -> str:
    normalized = normalize_whitespace(text)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}..."
