import json
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "compliance_rules.json"


def check_workflow_compliance(task: str, workflow: dict[str, Any]) -> dict[str, Any]:
    rules = load_compliance_rules()
    if not rules:
        return {
            "passed": True,
            "warnings": [],
            "summary": "未加载合规规则",
        }

    workflow_text = build_workflow_text(task, workflow)
    warnings: list[dict[str, Any]] = []

    for rule in rules:
        trigger_keywords = get_keyword_list(rule, "trigger_keywords")
        required_keywords = get_keyword_list(rule, "required_keywords")
        matched_triggers = find_matched_keywords(workflow_text, trigger_keywords)
        if not matched_triggers:
            continue

        matched_required = find_matched_keywords(workflow_text, required_keywords)
        if matched_required:
            continue

        warnings.append(
            {
                "rule_id": str(rule.get("id", "")),
                "name": str(rule.get("name", "")),
                "level": str(rule.get("level", "medium")),
                "message": str(rule.get("message", "")),
                "matched_triggers": matched_triggers,
                "missing_required": required_keywords,
            }
        )

    return {
        "passed": not warnings,
        "warnings": warnings,
        "summary": build_summary(warnings),
    }


def load_compliance_rules() -> list[dict[str, Any]]:
    if not RULES_PATH.exists():
        return []

    try:
        with RULES_PATH.open("r", encoding="utf-8") as file:
            rules = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(rules, list):
        return []

    return [rule for rule in rules if isinstance(rule, dict)]


def build_workflow_text(task: str, workflow: dict[str, Any]) -> str:
    parts: list[str] = [task]
    parts.append(str(workflow.get("title", "")))
    parts.append(str(workflow.get("summary", "")))
    parts.extend(flatten_text_items(workflow.get("tools", [])))
    parts.extend(flatten_text_items(workflow.get("safety_notices", [])))
    parts.extend(flatten_steps(workflow.get("steps", [])))
    parts.extend(flatten_text_items(workflow.get("final_check", [])))
    return " ".join(part for part in parts if part)


def flatten_steps(steps: Any) -> list[str]:
    if not isinstance(steps, list):
        return []

    parts: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            parts.append(str(step))
            continue
        parts.extend(
            [
                str(step.get("title", "")),
                str(step.get("description", "")),
                str(step.get("check_item", "")),
                str(step.get("risk", "")),
                str(step.get("reference", "")),
            ]
        )
    return parts


def flatten_text_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def get_keyword_list(rule: dict[str, Any], field: str) -> list[str]:
    value = rule.get(field, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def find_matched_keywords(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def build_summary(warnings: list[dict[str, Any]]) -> str:
    if not warnings:
        return "合规校验通过"
    return f"发现 {len(warnings)} 条合规风险，请补充安全与规范要求"
