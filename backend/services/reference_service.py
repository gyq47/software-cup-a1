import re
from typing import Any

MAX_REFERENCE_CONTENT_CHARS = 300
MAX_STEP_REFERENCES = 2
MIN_KEYWORD_LENGTH = 2
INSUFFICIENT_REFERENCE_TEXT = "知识库依据不足"


def attach_step_references(
    workflow: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    steps = workflow.get("steps", [])
    if not isinstance(steps, list):
        workflow["evidence_summary"] = build_evidence_summary(contexts, [])
        return workflow

    low_evidence_steps: list[int] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue

        step_no = int(step.get("step_no") or index)
        matched_references = match_step_references(step, contexts)
        step["references"] = matched_references
        if not matched_references or is_insufficient_reference(step.get("reference")):
            low_evidence_steps.append(step_no)

    workflow["evidence_summary"] = build_evidence_summary(contexts, low_evidence_steps)
    return workflow


def match_step_references(
    step: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    step_text = " ".join(
        [
            str(step.get("title", "")),
            str(step.get("description", "")),
            str(step.get("check_item", "")),
        ]
    )
    step_keywords = extract_keywords(step_text)
    if not step_keywords:
        return []

    scored_contexts: list[tuple[int, float, dict[str, Any]]] = []
    for context in contexts:
        content = str(context.get("content", ""))
        content_keywords = extract_keywords(content)
        overlap = step_keywords & content_keywords
        if not overlap:
            continue

        score = len(overlap) * 10 + float(context.get("final_score") or 0)
        scored_contexts.append((len(overlap), score, context))

    scored_contexts.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        build_reference_payload(context)
        for _overlap_count, _score, context in scored_contexts[:MAX_STEP_REFERENCES]
    ]


def build_reference_payload(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": context.get("filename", ""),
        "page": context.get("page", ""),
        "page_number": context.get("page_number", context.get("page", "")),
        "pdf_filename": context.get("pdf_filename", context.get("filename", "")),
        "page_image_path": context.get("page_image_path", ""),
        "preview_available": bool(context.get("page_image_path") and context.get("source_type", "manual_text") != "feedback_case"),
        "preview_url": context.get("preview_url", ""),
        "chunk_id": context.get("chunk_id", ""),
        "content": truncate_text(str(context.get("content", "")), MAX_REFERENCE_CONTENT_CHARS),
        "final_score": context.get("final_score", 0),
        "bm25_score": context.get("bm25_score", 0),
        "keyword_hits": context.get("keyword_hits", 0),
        "semantic_score": context.get("semantic_score", 0),
        "source_type": context.get("source_type", "manual_text"),
        "case_id": context.get("case_id", ""),
        "device_model": context.get("device_model", ""),
    }


def build_evidence_summary(
    contexts: list[dict[str, Any]],
    low_evidence_steps: list[int],
) -> dict[str, Any]:
    pages = sorted({str(context.get("page")) for context in contexts if context.get("page")})
    files = sorted({str(context.get("filename")) for context in contexts if context.get("filename")})
    return {
        "total_contexts": len(contexts),
        "referenced_pages": pages,
        "main_files": files,
        "low_evidence_steps": low_evidence_steps,
    }


def extract_keywords(text: str) -> set[str]:
    normalized = text.lower()
    return {
        keyword
        for keyword in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", normalized)
        if len(keyword) >= MIN_KEYWORD_LENGTH
    }


def truncate_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}..."


def is_insufficient_reference(reference: Any) -> bool:
    text = str(reference or "").strip()
    return not text or INSUFFICIENT_REFERENCE_TEXT in text
