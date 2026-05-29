import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.services.case_indexing_service import index_feedback_case

BASE_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FEEDBACK_FILE = BASE_DATA_DIR / "feedback" / "feedback_items.json"
CASE_FILE = BASE_DATA_DIR / "cases" / "case_items.json"

INDUSTRIAL_KEYWORDS = [
    "火花塞",
    "离合器",
    "机油",
    "漏油",
    "发动机",
    "启动困难",
    "异响",
    "气门",
    "活塞",
    "扭矩",
    "断电",
    "安全",
    "检查",
    "安装",
    "拆卸",
    "更换",
]
MAX_KEYWORDS = 10


def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    now = get_now()
    feedback_id = f"fb_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    item = {
        "feedback_id": feedback_id,
        "source_type": payload.get("source_type", ""),
        "source_id": payload.get("source_id", ""),
        "original_question": payload.get("original_question", ""),
        "original_answer": payload.get("original_answer", ""),
        "correction_type": payload.get("correction_type", "other"),
        "correction_text": payload.get("correction_text", ""),
        "related_device": payload.get("related_device", ""),
        "related_fault": payload.get("related_fault", ""),
        "submitter_role": payload.get("submitter_role", "worker"),
        "priority": payload.get("priority", "medium"),
        "status": "pending",
        "review_comment": "",
        "reviewer": "",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    items = read_json_list(FEEDBACK_FILE)
    items.append(item)
    write_json_list(FEEDBACK_FILE, items)

    return {
        "success": True,
        "feedback_id": feedback_id,
        "status": "pending",
        "message": "修正已提交，等待专家审核",
    }


def get_pending_feedback() -> dict[str, list[dict[str, Any]]]:
    items = read_json_list(FEEDBACK_FILE)
    return {"items": [item for item in items if item.get("status") == "pending"]}


def review_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    feedback_id = str(payload.get("feedback_id", ""))
    action = str(payload.get("action", ""))
    if action not in {"approve", "reject"}:
        raise ValueError("action 只能是 approve 或 reject")

    items = read_json_list(FEEDBACK_FILE)
    for item in items:
        if item.get("feedback_id") != feedback_id:
            continue

        now = get_now().isoformat()
        item["status"] = "approved" if action == "approve" else "rejected"
        item["review_comment"] = payload.get("review_comment", "")
        item["reviewer"] = payload.get("reviewer", "expert")
        item["updated_at"] = now
        write_json_list(FEEDBACK_FILE, items)

        if action == "approve":
            case = create_case_from_feedback(item)
            index_result = safely_index_feedback_case(case, item)
            return {
                "success": True,
                "status": "approved",
                "case_id": case.get("case_id", ""),
                "rag_indexed": bool(index_result.get("indexed", False)),
                "index_message": str(index_result.get("message", "")),
                "message": build_review_success_message(index_result),
            }

        return {
            "success": True,
            "status": "rejected",
            "message": "反馈已驳回",
        }

    raise ValueError("未找到对应反馈")


def get_cases() -> dict[str, list[dict[str, Any]]]:
    return {"items": read_json_list(CASE_FILE)}


def create_case_from_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
    now = get_now()
    case_id = f"case_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    keyword_text = " ".join(
        [
            str(feedback.get("correction_text", "")),
            str(feedback.get("original_question", "")),
            str(feedback.get("related_fault", "")),
        ]
    )
    case = {
        "case_id": case_id,
        "title": build_case_title(feedback),
        "source_feedback_id": feedback.get("feedback_id", ""),
        "device": feedback.get("related_device", ""),
        "fault": feedback.get("related_fault", ""),
        "correction_text": feedback.get("correction_text", ""),
        "keywords": extract_keywords(keyword_text),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "status": "approved",
    }

    cases = read_json_list(CASE_FILE)
    cases.append(case)
    write_json_list(CASE_FILE, cases)
    return case


def safely_index_feedback_case(case: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    try:
        return index_feedback_case(case, feedback)
    except Exception as exc:
        print(f"[Feedback RAG] case indexing failed. reason: {exc}")
        return {
            "indexed": False,
            "message": "审核案例保存成功，但写入 RAG 知识库失败",
        }


def build_review_success_message(index_result: dict[str, Any]) -> str:
    if index_result.get("indexed"):
        return "反馈已审核通过，已生成知识案例并写入 RAG 知识库"
    return "反馈已审核通过，已生成知识案例；RAG 索引写入失败，请稍后重新索引"


def extract_keywords(text: str) -> list[str]:
    normalized = text.strip()
    keywords: list[str] = []

    for keyword in INDUSTRIAL_KEYWORDS:
        if keyword in normalized and keyword not in keywords:
            keywords.append(keyword)

    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_/-]{2,}", normalized):
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= MAX_KEYWORDS:
            break

    return keywords[:MAX_KEYWORDS]


def build_case_title(feedback: dict[str, Any]) -> str:
    fault = str(feedback.get("related_fault", "")).strip()
    question = str(feedback.get("original_question", "")).strip()
    if fault:
        return f"{fault}修正案例"
    if question:
        return f"{question}修正案例"
    return "人工修正知识案例"


def read_json_list(path: Path) -> list[dict[str, Any]]:
    ensure_json_file(path)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def write_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def ensure_json_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_json_list(path, [])


def get_now() -> datetime:
    return datetime.now().replace(microsecond=0)
