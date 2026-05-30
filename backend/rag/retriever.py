from typing import Any

from backend.rag.metadata_service import extract_filters_from_query, normalize_device_model
from backend.rag.vector_store import get_vector_store

POLLUTION_KEYWORDS = (
    "程序段",
    "变量",
    "宏变量",
    "R参数",
    "TABLE",
    "G代码",
    "M代码",
    "ISO",
    "子程序",
    "NC程序",
    "M功能",
    "G功能",
    "N10",
    "N20",
    "N30",
    "DEF",
    "PROC",
)
DIAGNOSTIC_KEYWORDS = (
    "故障",
    "报警",
    "无法",
    "不能",
    "失败",
    "异常",
    "回零",
    "回参考点",
    "急停",
    "伺服",
    "驱动",
    "不动作",
    "无法启动",
    "报警号",
)
PROGRAMMING_KEYWORDS = (
    "PLC",
    "子程序",
    "程序",
    "G代码",
    "M代码",
    "R参数",
    "宏变量",
    "ISO",
    "变量",
    "TABLE",
)
DIAGNOSTIC_STAGES = (
    ("diagnostic-primary", ("diagnosis", "electrical", "drive", "feedback_case")),
    ("diagnostic-parameter", ("parameter",)),
    ("diagnostic-all", ()),
)
PROGRAMMING_STAGES = (
    ("programming-primary", ("plc", "parameter", "operation")),
    ("programming-all", ()),
)


def retrieve_documents(
    query: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[tuple[Any, float]]:
    results, _filter_info = retrieve_documents_with_info(query, top_k=top_k, filters=filters)
    return results


def retrieve_documents_with_info(
    query: str,
    top_k: int = 5,
    filters: dict[str, Any] | None = None,
) -> tuple[list[tuple[Any, float]], dict[str, Any]]:
    filter_info = build_filter_info(filters)
    if not query.strip():
        return [], filter_info

    vector_store = get_vector_store()
    if vector_store is None:
        filter_info["filter_fallback"] = True
        filter_info["filter_message"] = "向量库不可用，已进入降级模式"
        return [], filter_info

    resolved_filters = dict(filters or {})
    resolved_filters.update({key: value for key, value in extract_filters_from_query(query).items() if value})
    normalized_device_model = normalize_device_model(resolved_filters.get("device_model"))
    if normalized_device_model:
        resolved_filters["device_model"] = normalized_device_model
        filter_info["used_device_filter"] = True
        filter_info["requested_device_model"] = normalized_device_model

    print(f"[LangChain RAG] retrieving top_k={top_k}")
    try:
        intent = detect_query_intent(query)
        print(f"[Retriever] intent={intent}")

        if normalized_device_model:
            filtered_results = run_intent_search(
                vector_store=vector_store,
                query=query,
                top_k=top_k,
                intent=intent,
                base_filters={"device_model": normalized_device_model},
            )
            if filtered_results:
                filter_info["filter_message"] = f"已优先使用设备型号 {normalized_device_model} 的知识来源"
                return attach_filter_info(filtered_results, filter_info), filter_info

            filter_info["filter_fallback"] = True
            filter_info["filter_message"] = "当前设备型号下依据不足，已扩展到全库检索"

        results = run_intent_search(
            vector_store=vector_store,
            query=query,
            top_k=top_k,
            intent=intent,
            base_filters={key: value for key, value in resolved_filters.items() if key != "device_model"},
        )
        return attach_filter_info(results, filter_info), filter_info
    except Exception as exc:
        print(f"[LangChain RAG] fallback to legacy search. reason: {exc}")
        return [], filter_info


def build_filter_info(filters: dict[str, Any] | None) -> dict[str, Any]:
    requested_device_model = normalize_device_model((filters or {}).get("device_model"))
    return {
        "used_device_filter": bool(requested_device_model),
        "filter_fallback": False,
        "filter_message": "",
        "requested_device_model": requested_device_model,
    }


def run_intent_search(
    vector_store: Any,
    query: str,
    top_k: int,
    intent: str,
    base_filters: dict[str, Any] | None = None,
) -> list[tuple[Any, float]]:
    if intent == "diagnostic":
        return staged_manual_type_search(vector_store, query, top_k, DIAGNOSTIC_STAGES, base_filters)

    if intent == "programming":
        return staged_manual_type_search(vector_store, query, top_k, PROGRAMMING_STAGES, base_filters)

    results = search_with_filter(vector_store, query, top_k, base_filters or {})
    return results or vector_store.similarity_search_with_score(query, k=top_k)


def search_with_filter(
    vector_store: Any,
    query: str,
    top_k: int,
    filters: dict[str, Any],
) -> list[tuple[Any, float]]:
    if not filters:
        return []
    where_filter = build_chroma_filter(filters)
    try:
        results = vector_store.similarity_search_with_score(query, k=top_k, filter=where_filter)
        if results:
            return results
    except Exception:
        pass

    try:
        candidates = vector_store.similarity_search_with_score(query, k=max(top_k * 8, 30))
        filtered = [item for item in candidates if metadata_matches_filters(getattr(item[0], "metadata", {}), filters)]
        return filtered[:top_k]
    except Exception:
        return []


def build_chroma_filter(filters: dict[str, Any]) -> dict[str, Any]:
    items = [{key: value} for key, value in filters.items() if value]
    if not items:
        return {}
    if len(items) == 1:
        return items[0]
    return {"$and": items}


def metadata_matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if key == "device_model":
            if normalize_device_model(metadata.get(key)) != normalize_device_model(value):
                return False
            continue
        if str(metadata.get(key, "")) != str(value):
            return False
    return True


def attach_filter_info(
    results: list[tuple[Any, float]],
    filter_info: dict[str, Any],
) -> list[tuple[Any, float]]:
    for document, _score in results:
        metadata = getattr(document, "metadata", {})
        metadata.update(
            {
                "used_device_filter": filter_info.get("used_device_filter", False),
                "filter_fallback": filter_info.get("filter_fallback", False),
                "filter_message": filter_info.get("filter_message", ""),
                "requested_device_model": filter_info.get("requested_device_model", ""),
            }
        )
    return results


def search_with_any_filter(
    vector_store: Any,
    query: str,
    top_k: int,
    filters: dict[str, Any],
) -> list[tuple[Any, float]]:
    for key, value in filters.items():
        try:
            results = vector_store.similarity_search_with_score(query, k=top_k, filter={key: value})
            if results:
                return results
        except Exception:
            continue
    return []


def staged_manual_type_search(
    vector_store: Any,
    query: str,
    top_k: int,
    stages: tuple[tuple[str, tuple[str, ...]], ...],
    base_filters: dict[str, Any] | None = None,
) -> list[tuple[Any, float]]:
    merged_results: list[tuple[Any, float]] = []
    seen_chunk_ids: set[str] = set()

    for stage, manual_types in stages:
        print(f"[Retriever] stage={stage}")
        print(f"[Retriever] manual_types={manual_types or ('all',)}")

        stage_results = search_by_manual_types(
            vector_store=vector_store,
            query=query,
            top_k=max(top_k - len(merged_results), 1),
            manual_types=manual_types,
            base_filters=base_filters or {},
        )
        append_unique_results(merged_results, seen_chunk_ids, stage_results, top_k)
        if len(merged_results) >= top_k:
            break

    return rerank_results_by_pollution(merged_results[:top_k], detect_query_intent(query))


def search_by_manual_types(
    vector_store: Any,
    query: str,
    top_k: int,
    manual_types: tuple[str, ...],
    base_filters: dict[str, Any] | None = None,
) -> list[tuple[Any, float]]:
    base_filters = dict(base_filters or {})
    if not manual_types:
        return search_with_filter(vector_store, query, top_k, base_filters) if base_filters else vector_store.similarity_search_with_score(query, k=top_k)

    results: list[tuple[Any, float]] = []
    for manual_type in manual_types:
        filters = {**base_filters, "manual_type": manual_type}
        try:
            results.extend(search_with_filter(vector_store, query, top_k, filters))
        except Exception:
            continue

    return sorted(results, key=lambda item: item[1])[:top_k]


def append_unique_results(
    merged_results: list[tuple[Any, float]],
    seen_chunk_ids: set[str],
    stage_results: list[tuple[Any, float]],
    top_k: int,
) -> None:
    for document, score in stage_results:
        chunk_id = str(getattr(document, "metadata", {}).get("chunk_id", ""))
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        merged_results.append((document, score))
        if len(merged_results) >= top_k:
            break


def detect_query_intent(query: str) -> str:
    upper_query = query.upper()
    if any(keyword.upper() in upper_query for keyword in PROGRAMMING_KEYWORDS):
        return "programming"
    if any(keyword.upper() in upper_query for keyword in DIAGNOSTIC_KEYWORDS):
        return "diagnostic"
    return "general"


def calculate_pollution_score(text: str) -> int:
    upper_text = text.upper()
    return sum(upper_text.count(keyword.upper()) for keyword in POLLUTION_KEYWORDS)


def rerank_results_by_pollution(
    results: list[tuple[Any, float]],
    intent: str,
) -> list[tuple[Any, float]]:
    if intent != "diagnostic":
        return results

    reranked: list[tuple[float, tuple[Any, float]]] = []
    for document, score in results:
        metadata = getattr(document, "metadata", {})
        content = str(getattr(document, "page_content", ""))
        pollution_score = calculate_pollution_score(content)
        final_score = 1 / (1 + max(float(score or 0), 0))
        adjusted_score = final_score - pollution_score * 0.03

        metadata["pollution_score"] = pollution_score
        metadata["adjusted_score"] = round(adjusted_score, 4)
        print(f"[Retriever] pollution_score={pollution_score}, adjusted_score={adjusted_score:.4f}")

        reranked.append((adjusted_score, (document, score)))

    reranked.sort(key=lambda item: item[0], reverse=True)
    return [result for _adjusted_score, result in reranked]
