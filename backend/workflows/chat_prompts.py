from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = (
    "你是中国软件杯 A1 工业设备检修知识检索与作业系统的检修助手。"
    "你只能依据给定维修手册片段、已审核反馈案例、已有知识图谱关系和图像分析结果回答。"
    "必须严格区分 SINUMERIK 808D 与 SINUMERIK 828D。"
    "不得编造报警码、参数号、接线端子、页码、工具、扭矩、步骤或故障原因。"
    "维修手册证据优先；图谱只能作为辅助排查线索；反馈案例只能作为历史参考。"
    "证据不足时必须说明“现有知识库依据不足，不能作为标准作业依据”。"
    "涉及检修操作时必须提示停机、断电、挂牌、防误启动和人工复核。"
)

SOURCE_RULES = (
    "引用规则：\n"
    "1. 每个关键判断尽量引用维修手册来源。\n"
    "2. 来源格式使用：文件名 第X页 chunk_id=... 设备=...。\n"
    "3. 图谱关系不能替代手册证据。\n"
    "4. 历史反馈案例不能替代标准作业依据。\n"
    "5. 没有来源时必须明确说明依据不足。"
)

SAFETY_RULES = (
    "安全规则：\n"
    "1. 不知道就说不知道，不得用常识补全手册缺失内容。\n"
    "2. 不允许编造报警码、参数号、接线端子和手册页码。\n"
    "3. 检修前必须提示停机、断电、挂牌、防误启动。\n"
    "4. 高风险或证据不足时建议由设备工程师人工复核。"
)

OUTPUT_FORMAT = (
    "请按以下结构输出：\n"
    "## 现象判断\n"
    "## 可能原因\n"
    "## 排查步骤\n"
    "## 引用来源\n"
    "## 风险提醒\n"
    "## 下一步操作"
)


def build_graph_context_section(graph_context: dict[str, Any]) -> str:
    if not graph_context or not graph_context.get("enabled"):
        warning = ", ".join(str(item) for item in graph_context.get("warnings", []) if item) if graph_context else ""
        return f"关联知识图谱摘要：未匹配到可用图谱路径。{warning}"
    return (
        "关联知识图谱摘要：\n"
        "以下关系来自已有 graph.json 和检索结果匹配，只能作为排查线索，不能单独作为标准作业依据。\n"
        f"{graph_context.get('graph_context_text') or ''}"
    )


def build_vision_context_section(vision_context: dict[str, Any]) -> str:
    if not vision_context or not vision_context.get("enabled"):
        return "图像分析结果：未提供图片或视觉分析不可用。"
    return (
        "图像分析结果：图像识别可能误判，必须结合用户确认和维修手册证据。\n"
        f"{json.dumps(vision_context.get('result', vision_context), ensure_ascii=False)}"
    )


def build_answer_prompt(
    query: str,
    device_model: str,
    query_info: dict[str, Any],
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any],
    vision_context: dict[str, Any],
    feedback_cases: list[dict[str, Any]],
    diagnostics_context: dict[str, Any],
) -> str:
    return "\n\n".join(
        [
            f"用户问题：{query}",
            f"设备型号：{device_model or '未指定'}",
            f"识别到的查询信息：{json.dumps(query_info, ensure_ascii=False)}",
            f"维修手册证据：\n{format_contexts(contexts)}",
            build_graph_context_section(graph_context),
            build_vision_context_section(vision_context),
            f"历史审核案例：\n{format_feedback_cases(feedback_cases)}",
            f"诊断上下文：{json.dumps(diagnostics_context, ensure_ascii=False)}",
            SOURCE_RULES,
            SAFETY_RULES,
            OUTPUT_FORMAT,
        ]
    )


def format_contexts(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return "未命中维修手册片段。"
    lines: list[str] = []
    for index, context in enumerate(contexts, start=1):
        lines.append(
            f"[{index}] 文件：{context.get('pdf_filename') or context.get('filename') or '未知文件'}；"
            f"页码：{context.get('page_number') or context.get('page') or '未知'}；"
            f"chunk_id={context.get('chunk_id') or ''}；"
            f"设备={context.get('device_model') or '未标注'}\n"
            f"{context.get('content') or ''}"
        )
    return "\n\n".join(lines)


def format_feedback_cases(cases: list[dict[str, Any]]) -> str:
    if not cases:
        return "未匹配到历史审核案例。"
    lines: list[str] = []
    for index, case in enumerate(cases, start=1):
        lines.append(
            f"[{index}] 案例：{case.get('title') or case.get('case_id') or '未命名案例'}；"
            f"设备={case.get('device_model') or '未标注'}；"
            f"故障={case.get('fault') or ''}\n{case.get('content') or ''}"
        )
    return "\n\n".join(lines)

