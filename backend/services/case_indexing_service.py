import json
from pathlib import Path
from typing import Any

from backend.rag.vector_store import add_documents_to_vector_store

BASE_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FEEDBACK_FILE = BASE_DATA_DIR / "feedback" / "feedback_items.json"
CASE_FILE = BASE_DATA_DIR / "cases" / "case_items.json"


def index_feedback_case(case: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    document = build_feedback_case_document(case, feedback)
    indexed = add_documents_to_vector_store([document])
    return {
        "indexed": indexed,
        "message": "审核案例已写入 RAG 知识库" if indexed else "审核案例保存成功，但写入 RAG 知识库失败",
    }


def index_existing_feedback_cases() -> dict[str, Any]:
    cases = read_json_list(CASE_FILE)
    feedback_items = read_json_list(FEEDBACK_FILE)
    feedback_by_id = {str(item.get("feedback_id", "")): item for item in feedback_items}
    documents: list[Any] = []

    for case in cases:
        if case.get("status") != "approved":
            continue
        feedback = feedback_by_id.get(str(case.get("source_feedback_id", "")), {})
        documents.append(build_feedback_case_document(case, feedback))

    indexed = add_documents_to_vector_store(documents) if documents else True
    return {
        "indexed": indexed,
        "case_count": len(documents),
        "message": "已重建审核案例索引" if indexed else "审核案例索引重建失败",
    }


def build_feedback_case_document(case: dict[str, Any], feedback: dict[str, Any]) -> Any:
    from langchain_core.documents import Document

    case_id = str(case.get("case_id", ""))
    feedback_id = str(feedback.get("feedback_id", ""))
    page_content = build_feedback_case_content(case, feedback)
    metadata = {
        "source_type": "feedback_case",
        "case_id": case_id,
        "chunk_id": f"feedback_case-{case_id}",
        "filename": case.get("title") or f"审核案例 {case_id}",
        "title": case.get("title", ""),
        "source": f"feedback_case:{case_id}",
        "device_model": case.get("device", "") or feedback.get("related_device", ""),
        "alarm_code": extract_alarm_code(feedback.get("related_fault", "") or feedback.get("original_question", "")),
        "created_at": case.get("created_at", ""),
        "reviewer": feedback.get("reviewer", ""),
        "reviewer_id": feedback.get("reviewer", ""),
        "original_feedback_id": feedback_id,
        "source_feedback_id": feedback_id,
        "manual_type": "feedback_case",
        "doc_type": "feedback_case",
        "page": "经验案例",
        "relative_path": f"backend/data/cases/{case_id}.json",
        "source_dir": "feedback",
        "status": case.get("status", "approved"),
    }
    return Document(page_content=page_content, metadata=metadata)


def build_feedback_case_content(case: dict[str, Any], feedback: dict[str, Any]) -> str:
    parts = [
        ("案例标题", case.get("title", "")),
        ("原始故障描述", feedback.get("related_fault", "") or case.get("fault", "")),
        ("用户问题", feedback.get("original_question", "")),
        ("AI 原回答", feedback.get("original_answer", "")),
        ("人工修正内容", feedback.get("correction_text", "") or case.get("correction_text", "")),
        ("最终处理方案", case.get("correction_text", "") or feedback.get("correction_text", "")),
        ("注意事项或补充说明", feedback.get("review_comment", "")),
        ("设备型号", case.get("device", "") or feedback.get("related_device", "")),
        ("关键词", "、".join(case.get("keywords", [])) if isinstance(case.get("keywords"), list) else ""),
    ]
    return "\n".join(f"{label}：{value}" for label, value in parts if str(value).strip())


def extract_alarm_code(text: Any) -> str:
    import re

    match = re.search(r"(?<!\d)[A-Z]?\d{4,6}(?!\d)", str(text or ""), flags=re.IGNORECASE)
    return match.group(0) if match else ""


def read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
