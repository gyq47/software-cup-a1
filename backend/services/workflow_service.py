import json
import re
from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.services.compliance_service import check_workflow_compliance
from backend.services.context_cleaner import clean_contexts
from backend.services.evidence_service import build_evidence_items
from backend.services.lazy_graphrag_service import build_lazy_graph_context
from backend.services.reference_service import attach_step_references
from backend.services.vector_service import hybrid_search

REQUIRED_WORKFLOW_KEYS = (
    "title",
    "summary",
    "tools",
    "safety_notices",
    "steps",
    "final_check",
    "references",
)
DEFAULT_INSUFFICIENT_TEXT = "知识库依据不足"


def generate_workflow_card(
    task: str,
    top_k: int = 5,
    device_model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    contexts = hybrid_search(task, top_k=top_k, device_model=device_model)
    graph_context = build_lazy_graph_context(task, contexts, device_model=device_model)
    cleaned_contexts = clean_contexts(task, contexts)
    workflow = normalize_workflow(request_workflow_from_qwen(task, cleaned_contexts, graph_context), task)
    workflow = attach_step_references(workflow, contexts)
    compliance_result = check_workflow_compliance(task, workflow)
    evidence_items = build_evidence_items(contexts)
    return workflow, compliance_result, contexts, evidence_items, graph_context


def request_workflow_from_qwen(
    task: str,
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY 未配置")

    client = OpenAI(
        api_key=QWEN_API_KEY,
        base_url=QWEN_BASE_URL,
    )

    try:
        response = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": build_workflow_system_prompt(),
                },
                {
                    "role": "user",
                    "content": build_workflow_user_prompt(task, contexts, graph_context),
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        raise RuntimeError("Qwen API 调用失败") from exc

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Qwen API 未返回有效作业卡")

    return parse_workflow_json(content)


def build_workflow_system_prompt() -> str:
    return (
        "你是工业设备检修标准作业卡编制专家。"
        "你只能依据给定维修手册上下文生成作业卡，不得使用常识补全。"
        "不得编造手册没有的步骤、工具、扭矩、间隙、参数、故障原因、零件型号或工艺要求。"
        "维修手册未明确提供该信息时，必须写“维修手册未明确提供该信息，不能作为标准作业依据”。"
        "如果某字段缺少依据，字段值写“知识库依据不足”。"
        "输出必须是合法 JSON，不要 Markdown，不要代码块，不要解释性文字。"
        "JSON 顶层必须包含 title、summary、tools、safety_notices、steps、final_check、references。"
        "steps 必须是数组，每项包含 step_no、title、description、check_item、risk、reference。"
        "reference 尽量使用“文件名 第X页”，没有依据则写“知识库依据不足”。"
        "安全提醒必须覆盖停机断电、防烫伤、防夹伤、使用合适工具、扭矩按手册要求执行。"
    )


def build_workflow_user_prompt(
    task: str,
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any] | None = None,
) -> str:
    context_text = format_workflow_contexts(contexts)
    if not context_text:
        context_text = DEFAULT_INSUFFICIENT_TEXT

    return (
        f"检修任务：{task}\n\n"
        f"知识库片段：\n{context_text}\n\n"
        f"关联知识图谱上下文：\n{format_workflow_graph_context(graph_context)}\n\n"
        "请生成标准化作业卡 JSON，格式如下：\n"
        "{\n"
        '  "title": "离合器安装标准作业卡",\n'
        '  "summary": "...",\n'
        '  "tools": ["..."],\n'
        '  "safety_notices": ["..."],\n'
        '  "steps": [\n'
        "    {\n"
        '      "step_no": 1,\n'
        '      "title": "...",\n'
        '      "description": "...",\n'
        '      "check_item": "...",\n'
        '      "risk": "...",\n'
        '      "reference": "文件名 第X页"\n'
        "    }\n"
        "  ],\n"
        '  "final_check": ["..."],\n'
        '  "references": ["..."]\n'
        "}"
    )


def format_workflow_contexts(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return ""

    formatted: list[str] = []
    for index, context in enumerate(contexts, start=1):
        filename = context.get("filename", "未知文件")
        page = context.get("page", "未知页码")
        chunk_id = context.get("chunk_id", "未知片段")
        final_score = context.get("final_score", "无")
        keyword_hits = context.get("keyword_hits", "无")
        bm25_score = context.get("bm25_score", "无")
        content = context.get("content", "")
        formatted.append(
            f"[{index}] 文件：{filename}；页码：{page}；chunk_id：{chunk_id}；"
            f"final_score：{final_score}；keyword_hits：{keyword_hits}；bm25_score：{bm25_score}\n"
            f"{content}"
        )
    return "\n\n".join(formatted)


def format_workflow_graph_context(graph_context: dict[str, Any] | None) -> str:
    if not graph_context or not graph_context.get("enabled"):
        return "未匹配到可用关联图谱节点。"
    return str(graph_context.get("graph_context_text") or "未匹配到可用关联图谱节点。")


def parse_workflow_json(content: str) -> dict[str, Any]:
    json_text = extract_json_text(content)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Qwen API 未返回合法 JSON 作业卡") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Qwen API 返回的作业卡格式无效")

    return parsed


def extract_json_text(content: str) -> str:
    stripped = content.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1]


def normalize_workflow(workflow: dict[str, Any], task: str) -> dict[str, Any]:
    normalized = {key: workflow.get(key, DEFAULT_INSUFFICIENT_TEXT) for key in REQUIRED_WORKFLOW_KEYS}
    normalized["title"] = normalize_text_field(normalized["title"], f"{task}标准作业卡")
    normalized["summary"] = normalize_text_field(normalized["summary"])
    normalized["tools"] = normalize_string_list(normalized["tools"])
    normalized["safety_notices"] = normalize_string_list(normalized["safety_notices"])
    normalized["steps"] = normalize_steps(normalized["steps"])
    normalized["final_check"] = normalize_string_list(normalized["final_check"])
    normalized["references"] = normalize_string_list(normalized["references"])
    normalized["evidence_summary"] = workflow.get("evidence_summary", {})
    return normalized


def normalize_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        return [build_insufficient_step(1)]

    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            normalized_steps.append(build_insufficient_step(index))
            continue
        normalized_steps.append(
            {
                "step_no": int(step.get("step_no") or index),
                "title": normalize_text_field(step.get("title")),
                "description": normalize_text_field(step.get("description")),
                "check_item": normalize_text_field(step.get("check_item")),
                "risk": normalize_text_field(step.get("risk")),
                "reference": normalize_text_field(step.get("reference")),
            }
        )
    return normalized_steps


def build_insufficient_step(step_no: int) -> dict[str, Any]:
    return {
        "step_no": step_no,
        "title": DEFAULT_INSUFFICIENT_TEXT,
        "description": DEFAULT_INSUFFICIENT_TEXT,
        "check_item": DEFAULT_INSUFFICIENT_TEXT,
        "risk": DEFAULT_INSUFFICIENT_TEXT,
        "reference": DEFAULT_INSUFFICIENT_TEXT,
    }


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
        return result or [DEFAULT_INSUFFICIENT_TEXT]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return [DEFAULT_INSUFFICIENT_TEXT]


def normalize_text_field(value: Any, default: str = DEFAULT_INSUFFICIENT_TEXT) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default
