import json
import re
from typing import Any

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.rag.retriever import retrieve_documents_with_info
from backend.services.diagnosis_service import (
    apply_confidence_to_structured_answer,
    evaluate_diagnosis_confidence,
)
from backend.services.lazy_graphrag_service import build_lazy_graph_context


STRICT_RAG_SYSTEM_PROMPT = (
    "你是工业设备检修助手。"
    "你只能依据给定维修手册上下文回答。"
    "不得使用常识补全。"
    "不得编造手册没有的步骤、工具、扭矩、间隙、参数、故障原因。"
    "如果依据不足，必须说明：维修手册未明确提供该信息，不能作为标准作业依据。"
    "回答宁可简短，也不能编造。"
    "关键结论必须尽量标注来源文件和页码。"
)
STRUCTURED_RAG_OUTPUT_PROMPT = (
    "请只输出合法 JSON，不要输出 Markdown、代码块或额外解释。"
    "JSON 必须包含以下字段："
    "{{"
    '"fault_summary":"",'
    '"possible_causes":[],'
    '"operation_steps":[],'
    '"risk_warnings":[],'
    '"required_tools":[],'
    '"manual_references":[]'
    "}}。"
    "字段要求："
    "fault_summary 为一句话故障判断；"
    "possible_causes 为字符串数组，只能写手册依据支持的原因；"
    "operation_steps 为对象数组，每项包含 step_no、title、description、reference；"
    "risk_warnings 为字符串数组；"
    "required_tools 为字符串数组，手册未明确工具时返回空数组；"
    "manual_references 为对象数组，每项包含 filename、page、chunk_id、evidence。"
    "如果维修手册依据不足，在相关字段中写明“维修手册未明确提供该信息，不能作为标准作业依据”。"
)


def generate_rag_contexts(
    question: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contexts, _filter_info = generate_rag_contexts_with_info(question, top_k=top_k, filters=filters)
    return contexts


def generate_rag_contexts_with_info(
    question: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    retrieved, filter_info = retrieve_documents_with_info(question, top_k=top_k, filters=filters)
    contexts = [
        document_to_context(document, score, index, filter_info)
        for index, (document, score) in enumerate(retrieved, start=1)
    ]
    return contexts, filter_info


def generate_rag_answer_with_info(
    question: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    answer, contexts, filter_info, _graph_context = generate_rag_answer_with_graph_info(
        question,
        top_k=top_k,
        filters=filters,
    )
    return answer, contexts, filter_info


def generate_rag_answer_with_graph_info(
    question: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    contexts, filter_info = generate_rag_contexts_with_info(question, top_k=top_k, filters=filters)
    device_model = str((filters or {}).get("device_model") or "")
    graph_context = build_lazy_graph_context(question, contexts, device_model=device_model)
    answer = build_rag_answer_from_contexts(question, contexts, graph_context=graph_context)
    return answer, contexts, filter_info, graph_context


def generate_rag_answer(
    question: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    answer, contexts, _filter_info = generate_rag_answer_with_info(question, top_k=top_k, filters=filters)
    return answer, contexts


def build_rag_answer_from_contexts(
    question: str,
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any] | None = None,
) -> str:
    if not contexts:
        return build_empty_rag_json()

    if not QWEN_API_KEY:
        return build_error_rag_json("QWEN_API_KEY 未配置，无法生成 RAG 回答。")

    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.runnables import RunnableLambda, RunnablePassthrough
        from langchain_openai import ChatOpenAI

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", STRICT_RAG_SYSTEM_PROMPT),
                (
                    "user",
                    "问题：{question}\n\n维修手册上下文：\n{context}\n\n关联知识图谱上下文：\n{graph_context}\n\n"
                    + STRUCTURED_RAG_OUTPUT_PROMPT,
                ),
            ]
        )
        llm = ChatOpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
            model=QWEN_MODEL,
            temperature=0.1,
        )
        chain = (
            {
                "question": RunnablePassthrough(),
                "context": RunnableLambda(lambda _: format_contexts_for_prompt(contexts)),
                "graph_context": RunnableLambda(lambda _: format_graph_context_for_prompt(graph_context)),
            }
            | prompt
            | llm
            | StrOutputParser()
        )
        return normalize_rag_json(chain.invoke(question), contexts, question)
    except Exception as exc:
        print(f"[LangChain RAG] fallback to legacy search. reason: {exc}")
        return build_empty_rag_json()


def document_to_context(
    document: Any,
    score: float,
    index: int,
    filter_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = getattr(document, "metadata", {}) or {}
    filter_info = filter_info or {}
    content = getattr(document, "page_content", "")
    chunk_id = metadata.get("chunk_id") or f"{metadata.get('filename', 'manual')}-p{metadata.get('page', 0)}-{index}"
    semantic_score = float(score or 0)
    final_score = round(1 / (1 + max(semantic_score, 0)), 4)
    return {
        "content": content,
        "filename": metadata.get("filename", ""),
        "page": metadata.get("page", ""),
        "page_number": metadata.get("page_number", metadata.get("page", "")),
        "pdf_filename": metadata.get("pdf_filename", metadata.get("filename", "")),
        "page_image_path": metadata.get("page_image_path", ""),
        "chunk_id": chunk_id,
        "source": metadata.get("source", ""),
        "source_type": metadata.get("source_type", "manual_text"),
        "case_id": metadata.get("case_id", ""),
        "original_feedback_id": metadata.get("original_feedback_id", metadata.get("source_feedback_id", "")),
        "reviewer": metadata.get("reviewer", ""),
        "alarm_code": metadata.get("alarm_code", ""),
        "brand": metadata.get("brand", ""),
        "device_model": metadata.get("device_model", ""),
        "manual_type": metadata.get("manual_type", ""),
        "doc_type": metadata.get("doc_type", metadata.get("manual_type", "")),
        "final_score": final_score,
        "keyword_hits": 0,
        "bm25_score": 0.0,
        "semantic_score": round(semantic_score, 4),
        "pollution_score": metadata.get("pollution_score", 0),
        "adjusted_score": metadata.get("adjusted_score", final_score),
        "used_device_filter": metadata.get("used_device_filter", filter_info.get("used_device_filter", False)),
        "filter_fallback": metadata.get("filter_fallback", filter_info.get("filter_fallback", False)),
        "filter_message": metadata.get("filter_message", filter_info.get("filter_message", "")),
        "requested_device_model": metadata.get("requested_device_model", filter_info.get("requested_device_model", "")),
    }


def format_contexts_for_prompt(contexts: list[dict[str, Any]]) -> str:
    formatted: list[str] = []
    for index, context in enumerate(contexts, start=1):
        formatted.append(
            f"[{index}] 文件：{context.get('filename', '未知文件')}；页码：{context.get('page', '未知')}；"
            f"chunk_id：{context.get('chunk_id', '')}\n{context.get('content', '')}"
        )
    return "\n\n".join(formatted)


def format_graph_context_for_prompt(graph_context: dict[str, Any] | None) -> str:
    if not graph_context or not graph_context.get("enabled"):
        return "未匹配到可用关联图谱节点。"
    return str(graph_context.get("graph_context_text") or "未匹配到可用关联图谱节点。")


def normalize_rag_json(
    raw_answer: str,
    contexts: list[dict[str, Any]] | None = None,
    query: str = "",
) -> str:
    try:
        payload = json.loads(raw_answer)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_answer, flags=re.DOTALL)
        if not match:
            return build_error_rag_json("模型未返回合法 JSON。")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return build_error_rag_json("模型未返回合法 JSON。")

    normalized = {
        "fault_summary": str(payload.get("fault_summary", "")),
        "possible_causes": ensure_list(payload.get("possible_causes")),
        "operation_steps": ensure_list(payload.get("operation_steps")),
        "risk_warnings": ensure_list(payload.get("risk_warnings")),
        "required_tools": ensure_list(payload.get("required_tools")),
        "manual_references": ensure_list(payload.get("manual_references")),
    }
    confidence = evaluate_diagnosis_confidence(
        contexts or [],
        contexts or [],
        normalized,
        query=query,
    )
    normalized = apply_confidence_to_structured_answer(normalized, confidence)
    return json.dumps(normalized, ensure_ascii=False)


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def build_empty_rag_json() -> str:
    return json.dumps(
        {
            "fault_summary": "维修手册未明确提供该信息，不能作为标准作业依据。",
            "possible_causes": [],
            "operation_steps": [],
            "risk_warnings": [],
            "required_tools": [],
            "manual_references": [],
            "diagnosis_confidence": "insufficient",
            "evidence_strength": "未检索到可用手册依据。",
            "manual_coverage": "未命中维修手册来源。",
            "fallback_notice": "手册依据不足，不能作为标准作业依据。",
        },
        ensure_ascii=False,
    )


def build_error_rag_json(message: str) -> str:
    return json.dumps(
        {
            "fault_summary": message,
            "possible_causes": [],
            "operation_steps": [],
            "risk_warnings": [],
            "required_tools": [],
            "manual_references": [],
            "diagnosis_confidence": "insufficient",
            "evidence_strength": "未形成可靠手册依据。",
            "manual_coverage": "未命中维修手册来源。",
            "fallback_notice": "手册依据不足，不能作为标准作业依据。",
        },
        ensure_ascii=False,
    )
