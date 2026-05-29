import json
import re
from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.services.context_cleaner import clean_contexts
from backend.services.evidence_service import build_evidence_items, build_grounding_result, build_retrieval_filter_result
from backend.services.lazy_graphrag_service import build_lazy_graph_context
from backend.services.tool_orchestrator_service import run_diagnosis_pipeline_trace
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
    mode: str | None = None,
    level: str | None = None,
    alarm_code: str | None = None,
) -> dict[str, Any]:
    enriched_text = " ".join([item for item in [alarm_code, text, level, mode] if item])
    vision_result = analyze_fault_image(
        image_bytes=image_bytes,
        content_type=content_type,
        text=enriched_text or text,
        device_model=device_model,
    )
    generated_query = build_multimodal_query(enriched_text or text, device_model, vision_result)
    contexts = hybrid_search(generated_query, top_k=5, device_model=device_model) if generated_query else []
    graph_context = build_lazy_graph_context(generated_query or text or "", contexts, device_model=device_model)
    cleaned_contexts = clean_contexts(generated_query or text or "", contexts)
    diagnosis = generate_diagnosis_report(
        generated_query=generated_query,
        vision_result=vision_result,
        contexts=cleaned_contexts,
        graph_context=graph_context,
    )
    diagnosis["generated_query"] = generated_query
    evidence_items = build_evidence_items(contexts)
    retrieval_filter = build_retrieval_filter_result(contexts)

    return {
        "vision_result": vision_result,
        "diagnosis": diagnosis,
        "contexts": contexts,
        "evidence_items": evidence_items,
        "grounding_result": build_grounding_result(contexts),
        "retrieval_filter": retrieval_filter,
        "structured_answer": build_structured_answer(diagnosis, evidence_items, contexts),
        "graph_context": graph_context,
        "graph_paths": graph_context.get("paths", []),
        "seed_nodes": graph_context.get("seed_nodes", []),
        "graph_enabled": bool(graph_context.get("enabled", False)),
        "graph_warnings": graph_context.get("warnings", []),
        "tool_trace": run_diagnosis_pipeline_trace(
            has_image=True,
            query=generated_query,
            vision_result=vision_result,
            contexts=contexts,
            retrieval_filter=retrieval_filter,
            graph_context=graph_context,
            diagnosis=diagnosis,
        ),
    }


def confirm_alarm_diagnosis(
    device_model: str | None = None,
    mode: str | None = None,
    level: str | None = None,
    selected_alarm_codes: list[str] | None = None,
    selected_alarm_texts: list[str] | None = None,
    user_confirm_note: str | None = None,
    fault_description: str | None = None,
    vision_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_vision_result = vision_result or {}
    confirmed_vision_result = build_confirmed_vision_result(
        current_vision_result,
        selected_alarm_codes or [],
        selected_alarm_texts or [],
        user_confirm_note,
    )
    query = build_confirmed_alarm_query(
        device_model=device_model,
        mode=mode,
        level=level,
        selected_alarm_codes=selected_alarm_codes or [],
        selected_alarm_texts=selected_alarm_texts or [],
        user_confirm_note=user_confirm_note,
        fault_description=fault_description,
        vision_result=confirmed_vision_result,
    )
    result = run_diagnosis_from_query(query, confirmed_vision_result, device_model=device_model)
    result["confirmed_alarm_codes"] = selected_alarm_codes or []
    result["confirmed_alarm_texts"] = selected_alarm_texts or []
    result["confirmed_query"] = query
    return result


def build_confirmed_alarm_query(
    device_model: str | None,
    mode: str | None,
    level: str | None,
    selected_alarm_codes: list[str],
    selected_alarm_texts: list[str],
    user_confirm_note: str | None,
    fault_description: str | None,
    vision_result: dict[str, Any],
) -> str:
    parts: list[str] = []
    parts.append(device_model or "")
    parts.extend(selected_alarm_codes)
    parts.extend(selected_alarm_texts)
    parts.append(remove_unselected_alarm_codes(user_confirm_note or "", selected_alarm_codes, vision_result))
    parts.append(remove_unselected_alarm_codes(fault_description or "", selected_alarm_codes, vision_result))
    parts.append(level or "")
    parts.append(mode or "")
    parts.append(str(vision_result.get("scene", "")))
    parts.extend(to_string_list(vision_result.get("visible_parts", [])))

    seen: set[str] = set()
    keywords: list[str] = []
    for part in parts:
        for token in extract_query_tokens(part):
            if token not in seen and token != "图像信息不足":
                seen.add(token)
                keywords.append(token)
    return " ".join(keywords)


def build_confirmed_vision_result(
    vision_result: dict[str, Any],
    selected_alarm_codes: list[str],
    selected_alarm_texts: list[str],
    user_confirm_note: str | None,
) -> dict[str, Any]:
    confirmed = dict(vision_result)
    confirmed["confirmed_alarm_codes"] = selected_alarm_codes
    confirmed["confirmed_alarm_texts"] = selected_alarm_texts
    confirmed["user_confirm_note"] = user_confirm_note or ""
    confirmed["diagnosis_scope"] = (
        "本次诊断仅围绕用户已确认的报警代码和补充说明展开，"
        "未选择的报警仅作为背景，不得作为主要诊断对象。"
    )
    return confirmed


def remove_unselected_alarm_codes(
    text: str,
    selected_alarm_codes: list[str],
    vision_result: dict[str, Any],
) -> str:
    if not text:
        return ""

    selected = {str(code).strip() for code in selected_alarm_codes if str(code).strip()}
    detected = set(to_string_list(vision_result.get("fault_codes", [])))
    for candidate in vision_result.get("alarm_candidates", []):
        if isinstance(candidate, dict):
            code = str(candidate.get("code", "")).strip()
            if code:
                detected.add(code)

    for code in detected - selected:
        text = re.sub(rf"(?<!\d){re.escape(code)}(?!\d)", "", text)
    return text


def run_diagnosis_from_query(
    query: str,
    vision_result: dict[str, Any],
    device_model: str | None = None,
) -> dict[str, Any]:
    contexts = hybrid_search(query, top_k=5, device_model=device_model) if query else []
    graph_context = build_lazy_graph_context(query, contexts, device_model=device_model)
    cleaned_contexts = clean_contexts(query, contexts)
    diagnosis = generate_diagnosis_report(
        generated_query=query,
        vision_result=vision_result,
        contexts=cleaned_contexts,
        graph_context=graph_context,
    )
    diagnosis["generated_query"] = query
    evidence_items = build_evidence_items(contexts)
    retrieval_filter = build_retrieval_filter_result(contexts)

    return {
        "vision_result": vision_result,
        "diagnosis": diagnosis,
        "contexts": contexts,
        "evidence_items": evidence_items,
        "grounding_result": build_grounding_result(contexts),
        "retrieval_filter": retrieval_filter,
        "structured_answer": build_structured_answer(diagnosis, evidence_items, contexts),
        "graph_context": graph_context,
        "graph_paths": graph_context.get("paths", []),
        "seed_nodes": graph_context.get("seed_nodes", []),
        "graph_enabled": bool(graph_context.get("enabled", False)),
        "graph_warnings": graph_context.get("warnings", []),
        "tool_trace": run_diagnosis_pipeline_trace(
            has_image=True,
            query=query,
            vision_result=vision_result,
            contexts=contexts,
            retrieval_filter=retrieval_filter,
            graph_context=graph_context,
            diagnosis=diagnosis,
        ),
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
    graph_context: dict[str, Any] | None = None,
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
                    "content": build_diagnosis_user_prompt(generated_query, vision_result, contexts, graph_context),
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
        "你只能依据图片识别结果和给定维修手册上下文回答，不得使用常识补全。"
        "不得编造手册没有的步骤、工具、扭矩、间隙、参数或故障原因。"
        "维修手册未明确提供该信息时，必须写“维修手册未明确提供该信息，不能作为标准作业依据”。"
        "偏故障诊断、专家辅助、可解释。"
        "不要输出 Markdown，只输出合法 JSON。"
        "如果知识库依据不足，必须在 summary 或建议中写“建议人工复核”。"
        "JSON 字段必须包含 summary、fault_analysis、inspection_steps、repair_suggestions、"
        "safety_notices、risk_level、workflow_recommended。risk_level 只能是 low、medium、high。"
    )


def build_diagnosis_user_prompt(
    generated_query: str,
    vision_result: dict[str, Any],
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any] | None = None,
) -> str:
    scope_text = ""
    if vision_result.get("confirmed_alarm_codes"):
        scope_text = (
            "诊断范围约束：本次诊断仅围绕用户已确认的报警代码和补充说明展开，"
            "未选择的报警仅作为背景，不得作为主要诊断对象。\n"
            f"已确认报警代码：{', '.join(to_string_list(vision_result.get('confirmed_alarm_codes')))}\n"
            f"已确认报警文本：{'；'.join(to_string_list(vision_result.get('confirmed_alarm_texts')))}\n"
            f"用户补充说明：{vision_result.get('user_confirm_note', '')}\n\n"
        )

    return (
        f"自动生成检索 query：{generated_query}\n\n"
        f"{scope_text}"
        f"图片识别结果：\n{json.dumps(vision_result, ensure_ascii=False)}\n\n"
        f"知识库片段：\n{format_contexts(contexts)}\n\n"
        f"关联知识图谱上下文：\n{format_graph_context(graph_context)}\n\n"
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


def format_graph_context(graph_context: dict[str, Any] | None) -> str:
    if not graph_context or not graph_context.get("enabled"):
        return "未匹配到可用关联图谱节点。"
    return str(graph_context.get("graph_context_text") or "未匹配到可用关联图谱节点。")


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


def build_structured_answer(
    diagnosis: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    structured_answer = {
        "fault_summary": diagnosis.get("summary", ""),
        "possible_causes": to_string_list(diagnosis.get("fault_analysis")),
        "operation_steps": build_operation_steps(diagnosis.get("inspection_steps")),
        "risk_warnings": to_string_list(diagnosis.get("safety_notices")),
        "required_tools": [],
        "manual_references": build_manual_references(evidence_items, contexts),
    }
    confidence = evaluate_diagnosis_confidence(
        contexts=contexts,
        evidence_items=evidence_items,
        structured_answer=structured_answer,
        query=str(diagnosis.get("generated_query", "")),
    )
    return apply_confidence_to_structured_answer(structured_answer, confidence)


def build_operation_steps(inspection_steps: Any) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(to_string_list(inspection_steps), start=1):
        steps.append(
            {
                "step": index,
                "step_no": index,
                "title": f"检查步骤 {index}",
                "action": step,
                "description": step,
                "reference": "",
            }
        )
    return steps


def build_manual_references(
    evidence_items: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_items = evidence_items or contexts
    references: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()

    for item in source_items:
        filename = item.get("filename") or item.get("source") or ""
        page = item.get("page", "")
        key = (str(filename), page)
        if key in seen:
            continue
        seen.add(key)
        references.append(
            {
                "file": filename,
                "filename": filename,
                "page": page,
                "page_number": item.get("page_number", page),
                "pdf_filename": item.get("pdf_filename", filename),
                "page_image_path": item.get("page_image_path", ""),
                "preview_available": item.get("preview_available", False),
                "preview_url": item.get("preview_url", ""),
                "chunk_id": item.get("chunk_id", ""),
                "evidence": item.get("summary") or item.get("content", "")[:180],
                "source_type": item.get("source_type", "manual_text"),
                "case_id": item.get("case_id", ""),
                "device_model": item.get("device_model", ""),
            }
        )

    return references


def evaluate_diagnosis_confidence(
    contexts: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    structured_answer: dict[str, Any],
    query: str = "",
) -> dict[str, Any]:
    context_count = len(contexts or [])
    evidence_count = len(evidence_items or [])
    context_text = " ".join(str(context.get("content", "")) for context in contexts)
    answer_text = json.dumps(structured_answer, ensure_ascii=False)
    query_codes = extract_alarm_codes(query)
    answer_codes = extract_alarm_codes(answer_text)
    has_explicit_alarm = bool(query_codes or answer_codes)
    has_diagnosis_manual = any(
        str(context.get("manual_type") or context.get("doc_type", "")).lower() == "diagnosis"
        for context in contexts
    )
    pollution_scores = [int(context.get("pollution_score") or 0) for context in contexts]
    max_pollution = max(pollution_scores, default=0)
    top_pollution = pollution_scores[0] if pollution_scores else 0
    avg_pollution = sum(pollution_scores) / len(pollution_scores) if pollution_scores else 0
    has_programming_pollution = max_pollution >= 10
    pages = {str(item.get("page", "")) for item in [*(evidence_items or []), *(contexts or [])] if item.get("page")}
    manual_files = {
        str(item.get("filename") or item.get("source") or "")
        for item in [*(evidence_items or []), *(contexts or [])]
        if item.get("filename") or item.get("source")
    }
    has_page_reference = bool(pages)
    weak_phrase_count = sum(
        context_text.count(phrase)
        for phrase in ("可能", "建议联系", "无法确定", "需检查", "请通知授权人员", "服务部门")
    )
    has_generic_reference = "知识库[1]" in answer_text or "知识库【1】" in answer_text
    has_specific_query = has_explicit_alarm or any(
        term in query
        for term in ("报警", "故障", "无法", "不能", "回零", "回参考点", "伺服", "驱动", "PLC", "轴", "主轴")
    )

    if context_count == 0 or evidence_count == 0 or not has_specific_query:
        level = "insufficient"
    elif has_explicit_alarm and has_diagnosis_manual and evidence_count >= 3 and top_pollution < 8 and avg_pollution < 12:
        level = "high"
    elif evidence_count >= 2 and (has_diagnosis_manual or has_explicit_alarm) and (top_pollution < 15 or avg_pollution < 15):
        level = "medium"
    elif context_count >= 1 and has_page_reference:
        level = "low"
    else:
        level = "insufficient"

    if has_generic_reference and level == "high":
        level = "medium"
    if weak_phrase_count >= 8 and level in {"high", "medium"}:
        level = "low"
    if has_programming_pollution and not has_explicit_alarm and level == "medium":
        level = "low"

    return {
        "diagnosis_confidence": level,
        "evidence_strength": build_evidence_strength(level, context_count, evidence_count, max_pollution),
        "manual_coverage": f"引用手册 {len(manual_files)} 个，涉及页码 {len(pages)} 个",
        "fallback_notice": build_fallback_notice(level),
        "evidence_metrics": {
            "contexts_count": context_count,
            "evidence_count": evidence_count,
            "manual_files_count": len(manual_files),
            "page_count": len(pages),
            "has_explicit_alarm": has_explicit_alarm,
            "has_diagnosis_manual": has_diagnosis_manual,
            "has_programming_pollution": has_programming_pollution,
            "max_pollution_score": max_pollution,
            "top_pollution_score": top_pollution,
            "avg_pollution_score": round(avg_pollution, 2),
            "weak_phrase_count": weak_phrase_count,
        },
    }


def apply_confidence_to_structured_answer(
    structured_answer: dict[str, Any],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    result = dict(structured_answer)
    result.update(confidence)
    level = confidence.get("diagnosis_confidence")
    if level == "insufficient":
        result["fault_summary"] = "当前知识库未检索到足够的标准维修依据，不能形成标准检修结论。"
        result["possible_causes"] = []
        result["operation_steps"] = []
        result["required_tools"] = []
        result["risk_warnings"] = [
            "手册依据不足，禁止直接按 AI 结果实施维修。",
            "请补充明确报警代码、设备型号或上传清晰报警界面后重新诊断。",
            *to_string_list(result.get("risk_warnings")),
        ]
    elif level == "low":
        result["fallback_notice"] = confidence.get("fallback_notice") or "手册依据较弱，以下内容仅供排查参考，不能直接作为标准作业依据。"
        result["risk_warnings"] = [
            "当前依据较弱，执行前必须由专业人员复核手册原文。",
            *to_string_list(result.get("risk_warnings")),
        ]
    return result


def extract_alarm_codes(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z]?\d{4,6}\b", text or "", flags=re.IGNORECASE))


def build_evidence_strength(level: str, context_count: int, evidence_count: int, max_pollution: int) -> str:
    if level == "high":
        return f"依据强：命中明确报警与诊断手册，证据片段 {evidence_count} 条，最大污染分 {max_pollution}。"
    if level == "medium":
        return f"依据中等：存在可用手册片段 {evidence_count} 条，仍需结合原文页码复核。"
    if level == "low":
        return f"依据较弱：召回片段 {context_count} 条，但报警或手册类型匹配不充分。"
    return "依据不足：未检索到足以支撑标准作业卡的可靠手册片段。"


def build_fallback_notice(level: str) -> str:
    if level == "insufficient":
        return "手册依据不足，不能生成可靠标准作业卡。"
    if level == "low":
        return "手册依据较弱，输出仅能作为人工排查线索。"
    return ""
