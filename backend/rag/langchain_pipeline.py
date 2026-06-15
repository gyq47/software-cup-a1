from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.rag.metadata_service import normalize_device_model
from backend.rag.rag_chain import generate_rag_contexts_with_info
from backend.services.evidence_service import build_evidence_items, build_grounding_result
from backend.services.evidence_service import build_retrieval_filter_result
from backend.services.lazy_graphrag_service import build_lazy_graph_context
from backend.services.tool_orchestrator_service import build_tool_result
from backend.services.tool_orchestrator_service import elapsed_ms
from backend.services.tool_orchestrator_service import run_chat_pipeline_trace

PROCESSED_CHUNKS_PATH = Path("backend/data/processed/manual_text_chunks_test_v2.jsonl").resolve()
EXACT_IDENTIFIER_PATTERN = re.compile(
    r"(\b\d{4,6}\b|MD\s*\d{4,6}|\$[A-Z0-9_]+|X\d{1,3}|I/O|PLC)",
    re.IGNORECASE,
)
KEYWORD_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_$/.:-]+")


def build_langchain_documents(chunks: list[dict[str, Any]]) -> list[Any]:
    Document = get_langchain_document_class()
    documents: list[Any] = []
    for chunk in chunks:
        content = str(chunk.get("content") or chunk.get("page_content") or "")
        if not content.strip():
            continue
        metadata = normalize_chunk_metadata(chunk.get("metadata") or chunk)
        documents.append(Document(page_content=content, metadata=metadata))
    return documents


def build_text_splitter(chunk_size: int = 900, chunk_overlap: int = 120) -> Any:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n报警 ",
            "\n\nMD",
            "\n\n$MA_",
            "\n\nX",
            "\n\nPLC",
            "\n\n",
            "\n",
            "。",
            "；",
            "，",
            " ",
            "",
        ],
        keep_separator=True,
    )


def build_langchain_retriever(
    top_k: int = 5,
    device_model: Optional[str] = None,
    manual_type: Optional[str] = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    normalized_device = normalize_device_model(device_model)
    if normalized_device:
        filters["device_model"] = normalized_device
    if manual_type:
        filters["manual_type"] = manual_type
    return {"search_kwargs": {"k": top_k, "filter": filters}, "retrieval_backend": "langchain_chroma"}


def parse_query_info(query: str, device_model: Optional[str] = None) -> dict[str, Any]:
    identifiers = sorted(set(match.group(0).replace(" ", "") for match in EXACT_IDENTIFIER_PATTERN.finditer(query)))
    normalized_device = normalize_device_model(device_model) or normalize_device_model(query)
    keywords = [token for token in KEYWORD_PATTERN.findall(query) if len(token.strip()) >= 2]
    return {
        "device_model": normalized_device,
        "alarm_codes": [item for item in identifiers if item.isdigit()],
        "md_parameters": [item for item in identifiers if item.upper().startswith("MD")],
        "variables": [item for item in identifiers if item.startswith("$")],
        "interfaces": [item for item in identifiers if item.upper().startswith("X") or item.upper() in {"PLC", "I/O"}],
        "identifiers": identifiers,
        "keywords": keywords,
    }


def run_langchain_chat(
    question: str,
    top_k: int = 5,
    device_model: Optional[str] = None,
) -> dict[str, Any]:
    query_info = parse_query_info(question, device_model)
    contexts, retrieval_filter = hybrid_retrieve_contexts(question, top_k=top_k, query_info=query_info)
    graph_context = build_lazy_graph_context(question, contexts, device_model=query_info.get("device_model") or "")

    llm_started_at = time.perf_counter()
    answer, degraded, llm_status, llm_error = generate_answer(question, contexts, graph_context, query_info)
    llm_duration = elapsed_ms(llm_started_at)

    tool_trace = run_chat_pipeline_trace(question, contexts, retrieval_filter, graph_context)
    tool_trace.append(build_llm_trace(degraded, llm_duration, llm_error))

    return {
        "answer": answer,
        "structured_answer": parse_structured_answer(answer),
        "contexts": contexts,
        "evidence_items": build_evidence_items(contexts),
        "grounding_result": build_grounding_result(contexts),
        "retrieval_filter": retrieval_filter,
        "graph_context": graph_context,
        "graph_paths": graph_context.get("paths", []),
        "seed_nodes": graph_context.get("seed_nodes", []),
        "graph_enabled": bool(graph_context.get("enabled", False)),
        "graph_warnings": graph_context.get("warnings", []),
        "tool_trace": tool_trace,
        "degraded": degraded,
        "model_status": llm_status,
        "llm_status": llm_status,
        "query_info": query_info,
    }


def hybrid_retrieve_contexts(
    question: str,
    top_k: int,
    query_info: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    device_model = query_info.get("device_model") or ""
    filters = {"device_model": device_model} if device_model else None
    contexts, filter_info = generate_rag_contexts_with_info(question, top_k=top_k, filters=filters)
    exact_contexts = exact_match_contexts(question, query_info, limit=max(top_k * 2, 10))
    merged = merge_and_rank_contexts(contexts, exact_contexts, query_info, top_k)
    merged, gate_info = apply_device_gate(merged, device_model)
    source_filter_fallback = bool(filter_info.get("filter_fallback", False))
    for context in merged:
        context["retrieval_backend"] = context.get("retrieval_backend") or "langchain_chroma"
        context["used_device_filter"] = bool(device_model)
        context["requested_device_model"] = device_model
        context["filter_fallback"] = bool(context.get("filter_fallback", source_filter_fallback))
        if device_model:
            context["filter_message"] = build_filter_message(
                device_model,
                context.get("filter_message") or filter_info.get("filter_message", ""),
                bool(context.get("filter_fallback", False)),
                gate_info,
            )
    filter_info = {
        **filter_info,
        "used_device_filter": bool(device_model),
        "requested_device_model": device_model,
        "filter_fallback": source_filter_fallback,
        "filter_message": build_filter_message(
            device_model,
            str(filter_info.get("filter_message") or ""),
            source_filter_fallback,
            gate_info,
        ),
        "retrieval_backend": detect_retrieval_backend(merged),
        **gate_info,
    }
    return merged, filter_info


def apply_device_gate(
    contexts: list[dict[str, Any]],
    requested_device_model: Optional[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested = normalize_device_model(requested_device_model)
    if not requested:
        return contexts, {
            "device_gate_applied": False,
            "device_gate_dropped_count": 0,
            "device_gate_dropped_devices": [],
        }

    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for context in contexts:
        if is_context_allowed_for_device(context, requested):
            kept.append(context)
        else:
            dropped.append(context)

    dropped_devices = sorted(
        {
            normalize_device_model(context.get("device_model")) or str(context.get("device_model") or "")
            for context in dropped
            if str(context.get("device_model") or "").strip()
        }
    )
    return kept, {
        "device_gate_applied": True,
        "device_gate_dropped_count": len(dropped),
        "device_gate_dropped_devices": dropped_devices,
    }


def is_context_allowed_for_device(context: dict[str, Any], requested_device_model: str) -> bool:
    current = normalize_device_model(context.get("device_model"))
    if not current:
        return True
    if is_common_device_model(current):
        return True
    return current == requested_device_model


def is_common_device_model(device_model: str) -> bool:
    value = str(device_model or "").strip().lower()
    return value in {"common", "general", "通用", "通用知识", "通用设备"}


def build_filter_message(
    device_model: str,
    existing_message: str,
    filter_fallback: bool,
    gate_info: dict[str, Any],
) -> str:
    if not device_model:
        return existing_message

    parts: list[str] = []
    if existing_message:
        parts.append(existing_message)
    elif filter_fallback:
        parts.append("当前设备型号下依据不足，已扩展检索范围")
    else:
        parts.append(f"已优先使用设备型号 {device_model} 的知识来源")

    dropped_count = int(gate_info.get("device_gate_dropped_count") or 0)
    if dropped_count > 0:
        dropped_devices = ", ".join(gate_info.get("device_gate_dropped_devices") or [])
        suffix = f"device gate 已过滤 {dropped_count} 条非目标设备片段"
        if dropped_devices:
            suffix += f"：{dropped_devices}"
        parts.append(suffix)
    return "；".join(parts)


def exact_match_contexts(question: str, query_info: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    identifiers = [identifier.upper() for identifier in query_info.get("identifiers", [])]
    keywords = [keyword.lower() for keyword in query_info.get("keywords", [])[:12]]
    device_model = normalize_device_model(query_info.get("device_model"))
    if not PROCESSED_CHUNKS_PATH.exists() or not (identifiers or keywords):
        return []

    matches: list[dict[str, Any]] = []
    with PROCESSED_CHUNKS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            metadata = normalize_chunk_metadata(payload.get("metadata") or {})
            if device_model and normalize_device_model(metadata.get("device_model")) != device_model:
                continue
            content = str(payload.get("content") or "")
            lower_content = content.lower()
            upper_content = content.upper()
            identifier_hits = sum(1 for item in identifiers if item and item in upper_content)
            keyword_hits = sum(1 for item in keywords if item and item in lower_content)
            if identifier_hits <= 0 and keyword_hits < 2:
                continue
            exact_score = identifier_hits * 100 + keyword_hits * 3
            matches.append(
                {
                    "content": content,
                    "filename": metadata.get("pdf_filename", metadata.get("filename", "")),
                    "pdf_filename": metadata.get("pdf_filename", metadata.get("filename", "")),
                    "page": metadata.get("page_number", metadata.get("page", "")),
                    "page_number": metadata.get("page_number", metadata.get("page", "")),
                    "chunk_id": metadata.get("chunk_id", ""),
                    "source_type": metadata.get("source_type", "manual_text"),
                    "device_model": normalize_device_model(metadata.get("device_model")),
                    "manual_type": metadata.get("manual_type", ""),
                    "section_title": metadata.get("section_title", ""),
                    "keyword_hits": keyword_hits + identifier_hits,
                    "bm25_score": exact_score,
                    "semantic_score": 0.0,
                    "final_score": exact_score,
                    "retrieval_backend": "langchain_hybrid_exact",
                }
            )
    return sorted(matches, key=lambda item: float(item.get("final_score", 0)), reverse=True)[:limit]


def merge_and_rank_contexts(
    vector_contexts: list[dict[str, Any]],
    exact_contexts: list[dict[str, Any]],
    query_info: dict[str, Any],
    top_k: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for context in vector_contexts:
        item = dict(context)
        item["final_score"] = float(item.get("final_score", 0.0)) + exact_boost(item, query_info)
        merged[str(item.get("chunk_id") or item.get("content", "")[:80])] = item
    for context in exact_contexts:
        key = str(context.get("chunk_id") or context.get("content", "")[:80])
        current = merged.get(key)
        if current is None or float(context.get("final_score", 0.0)) > float(current.get("final_score", 0.0)):
            merged[key] = context
    return sorted(merged.values(), key=lambda item: float(item.get("final_score", 0.0)), reverse=True)[:top_k]


def exact_boost(context: dict[str, Any], query_info: dict[str, Any]) -> float:
    content = str(context.get("content") or "").upper()
    boost = 0.0
    for identifier in query_info.get("identifiers", []):
        if str(identifier).upper() in content:
            boost += 100.0
    return boost


def generate_answer(
    question: str,
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any],
    query_info: dict[str, Any],
) -> tuple[str, bool, str, str]:
    if not contexts:
        return build_degraded_answer(contexts, graph_context, "未检索到足够的维修手册依据"), True, "unavailable", "无检索依据"
    if not QWEN_API_KEY:
        return build_degraded_answer(contexts, graph_context, "QWEN_API_KEY 未配置"), True, "unavailable", "QWEN_API_KEY 未配置"

    try:
        from openai import OpenAI

        messages = build_prompt_messages(question, contexts, graph_context, query_info)
        client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, timeout=30)
        response = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=messages,
            temperature=0.1,
        )
        answer = response.choices[0].message.content or ""
        if not answer.strip():
            raise RuntimeError("Qwen API 未返回有效回答")
        return answer, False, "available", ""
    except Exception as exc:
        reason = sanitize_error(exc)
        print(f"[LangChain Pipeline] LLM unavailable, return degraded answer. reason: {exc}")
        return build_degraded_answer(contexts, graph_context, reason), True, "unavailable", reason


def build_prompt_messages(
    question: str,
    contexts: list[dict[str, Any]],
    graph_context: dict[str, Any],
    query_info: dict[str, Any],
) -> list[dict[str, str]]:
    system_text = (
        "你是中国软件杯 A1 工业设备检修知识检索与作业系统的检修助手。"
        "只能依据给定证据回答，不得编造手册没有的步骤、参数、工具或结论。"
        "必须区分 808D/828D 设备型号，优先引用证据页码。"
        "证据不足时明确说明“手册依据不足，不能作为标准作业依据”。"
    )
    user_text = (
        f"用户问题：{question}\n"
        f"结构化 query_info：{json.dumps(query_info, ensure_ascii=False)}\n\n"
        f"检索证据：\n{format_contexts_for_prompt(contexts)}\n\n"
        f"关联图谱上下文：\n{graph_context.get('graph_context_text') or '未匹配到关联图谱节点。'}\n\n"
        "请输出检修判断、可能原因、检查步骤、安全提醒和参考依据。"
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=system_text),
                HumanMessage(content=user_text),
            ]
        )
        formatted = prompt.format_messages()
        return [message_to_openai_payload(message) for message in formatted]
    except Exception:
        return [{"role": "system", "content": system_text}, {"role": "user", "content": user_text}]


def message_to_openai_payload(message: Any) -> dict[str, str]:
    role = "user"
    message_type = getattr(message, "type", "")
    if message_type == "system":
        role = "system"
    elif message_type in {"ai", "assistant"}:
        role = "assistant"
    return {"role": role, "content": str(getattr(message, "content", ""))}


def format_contexts_for_prompt(contexts: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, context in enumerate(contexts, start=1):
        lines.append(
            f"[{index}] 设备：{context.get('device_model','')}；类型：{context.get('manual_type','')}；"
            f"文件：{context.get('pdf_filename') or context.get('filename','')}；页码：{context.get('page_number') or context.get('page','')}；"
            f"chunk_id：{context.get('chunk_id','')}\n{context.get('content','')}"
        )
    return "\n\n".join(lines)


def build_degraded_answer(contexts: list[dict[str, Any]], graph_context: dict[str, Any], reason: str) -> str:
    lines = [
        "当前大模型服务暂时不可用，系统已根据本地知识库检索到以下参考依据。",
        "请优先查看手册页码、来源片段和现场安全要求，必要时由设备工程师复核后再执行。",
        f"模型状态：{reason}",
    ]
    if contexts:
        lines.append("\n已检索到的参考依据：")
        for index, context in enumerate(contexts[:5], start=1):
            content = " ".join(str(context.get("content", "")).split())
            lines.append(
                f"{index}. 文件：{context.get('pdf_filename') or context.get('filename','未知文件')}；"
                f"页码：{context.get('page_number') or context.get('page','未知页码')}；"
                f"设备：{context.get('device_model','')}；片段：{content[:180]}"
            )
    paths = graph_context.get("paths") or []
    if paths:
        lines.append("\n关联图谱路径：")
        for path in paths[:5]:
            lines.append(f"- {path.get('source','')} --{path.get('relation','related_to')}--> {path.get('target','')}")
    lines.append("\n降级提示：当前结果不是大模型生成的完整诊断结论，请以手册原文和现场规程为准。")
    return "\n".join(lines)


def build_llm_trace(degraded: bool, duration_ms: int, error: str) -> dict[str, Any]:
    return build_tool_result(
        "LLMGenerationTool",
        "大模型回答生成工具",
        "failed" if degraded else "success",
        input_summary="LangChain Prompt + Qwen 生成检修回答",
        output_summary="大模型不可用，已返回本地证据降级结果" if degraded else "大模型回答生成完成",
        duration_ms=duration_ms,
        error=error or None,
        metadata={"degraded": degraded, "model_status": "unavailable" if degraded else "available"},
    )


def parse_structured_answer(answer: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_chunk_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    normalized["device_model"] = normalize_device_model(normalized.get("device_model"))
    normalized["manual_type"] = str(normalized.get("manual_type") or "other")
    normalized["pdf_filename"] = str(normalized.get("pdf_filename") or normalized.get("filename") or "")
    normalized["filename"] = str(normalized.get("filename") or normalized.get("pdf_filename") or "")
    normalized["page_number"] = normalized.get("page_number", normalized.get("page", ""))
    normalized["page"] = normalized["page_number"]
    normalized["source_type"] = str(normalized.get("source_type") or "manual_text")
    normalized["section_title"] = str(normalized.get("section_title") or "")
    normalized["heading_path"] = str(normalized.get("heading_path") or normalized.get("section_title") or "")
    return normalized


def get_langchain_document_class() -> Any:
    try:
        from langchain_core.documents import Document

        return Document
    except Exception:
        class SimpleDocument:
            def __init__(self, page_content: str, metadata: Optional[dict[str, Any]] = None) -> None:
                self.page_content = page_content
                self.metadata = metadata or {}

        return SimpleDocument


def detect_retrieval_backend(contexts: list[dict[str, Any]]) -> str:
    counter = Counter(str(context.get("retrieval_backend") or "langchain_chroma") for context in contexts)
    if not counter:
        return "langchain_chroma"
    return counter.most_common(1)[0][0]


def sanitize_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:180] + ("..." if len(message) > 180 else "")
