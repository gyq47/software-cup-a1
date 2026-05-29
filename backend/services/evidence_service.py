import re
from typing import Any
from urllib.parse import quote

MAX_EVIDENCE_CONTENT_CHARS = 500
MAX_EVIDENCE_SUMMARY_CHARS = 80


def build_evidence_items(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_items: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()

    for context in contexts:
        chunk_id = str(context.get("chunk_id") or "").strip()
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)

        content = normalize_whitespace(str(context.get("content", "")))
        source_type = str(context.get("source_type") or "manual_text")
        is_feedback_case = source_type == "feedback_case"
        is_manual_image = source_type == "manual_image"
        page_image_path = str(context.get("page_image_path") or "")
        preview_available = bool(page_image_path and not is_feedback_case)
        evidence_items.append(
            {
                "filename": context.get("filename", ""),
                "page": context.get("page", ""),
                "page_number": context.get("page_number", context.get("page", "")),
                "pdf_filename": context.get("pdf_filename", context.get("filename", "")),
                "page_image_path": page_image_path,
                "chunk_id": chunk_id,
                "content": truncate_text(content, MAX_EVIDENCE_CONTENT_CHARS),
                "summary": summarize_evidence_content(content),
                "final_score": context.get("final_score", 0),
                "keyword_hits": context.get("keyword_hits", 0),
                "bm25_score": context.get("bm25_score", 0),
                "semantic_score": context.get("semantic_score", 0),
                "source_type": source_type,
                "case_id": context.get("case_id", ""),
                "device_model": context.get("device_model", ""),
                "alarm_code": context.get("alarm_code", ""),
                "evidence_type": build_evidence_type(source_type),
                "source_label": build_source_label(source_type),
                "preview_available": preview_available,
                "preview_url": build_preview_url(page_image_path) if preview_available else "",
            }
        )

    return evidence_items


def build_grounding_result(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_items = build_evidence_items(contexts)
    pages = sorted({str(item.get("page")) for item in evidence_items if item.get("page")})
    files = sorted({str(item.get("filename")) for item in evidence_items if item.get("filename")})
    return {
        "grounded": bool(evidence_items),
        "evidence_count": len(evidence_items),
        "manual_files": files,
        "pages": pages,
        "summary": "已基于维修手册片段生成" if evidence_items else "维修手册未明确提供该信息，不能作为标准作业依据。",
    }


def build_retrieval_filter_result(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    first_context = contexts[0] if contexts else {}
    used_device_filter = bool(first_context.get("used_device_filter", False))
    filter_fallback = bool(first_context.get("filter_fallback", False))
    requested_device_model = str(first_context.get("requested_device_model", ""))
    filter_message = str(first_context.get("filter_message", ""))
    if used_device_filter and not filter_message:
        filter_message = f"已优先使用设备型号 {requested_device_model} 的知识来源"
    return {
        "used_device_filter": used_device_filter,
        "filter_fallback": filter_fallback,
        "filter_message": filter_message,
        "requested_device_model": requested_device_model,
    }


def summarize_evidence_content(content: str) -> str:
    if not content:
        return "该片段为维修手册命中依据。"

    sentence = re.split(r"[。；;.!?\n]", content, maxsplit=1)[0].strip()
    if not sentence:
        sentence = content.strip()
    return f"该片段主要涉及{truncate_text(sentence, MAX_EVIDENCE_SUMMARY_CHARS)}。"


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_preview_url(page_image_path: str) -> str:
    return f"/api/manual/page-image?path={quote(page_image_path)}"


def build_evidence_type(source_type: str) -> str:
    if source_type == "feedback_case":
        return "feedback_case"
    if source_type == "manual_image":
        return "manual_image"
    return "manual_text"


def build_source_label(source_type: str) -> str:
    if source_type == "feedback_case":
        return "审核案例"
    if source_type == "manual_image":
        return "手册图片"
    return "维修手册"
