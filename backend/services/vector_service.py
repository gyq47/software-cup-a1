from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import faiss
except Exception:
    faiss = None

try:
    import jieba
except Exception:
    jieba = None

try:
    import numpy as np
except Exception:
    np = None

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

from backend.core.config import RAG_BACKEND
from backend.rag.metadata_service import normalize_device_model
from backend.services.pdf_service import MANUAL_DIRS, load_manual_chunks

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDUSTRIAL_ACTION_TERMS = {
    "安装",
    "拆卸",
    "更换",
    "检查",
    "调整",
    "固定",
    "拧紧",
    "紧固",
    "测量",
    "润滑",
}
INDUSTRIAL_PART_TERMS = {
    "扭矩",
    "螺母",
    "螺栓",
    "离合器",
    "曲轴",
    "轴承",
    "转子",
    "垫片",
}
STEP_MARKERS = (
    "步骤",
    "安装步骤",
    "拆卸步骤",
    "注意",
    "确认",
    "检查",
    "1.",
    "2.",
    "3.",
    "（1）",
    "（2）",
    "①",
    "②",
)
for term in INDUSTRIAL_ACTION_TERMS | INDUSTRIAL_PART_TERMS:
    if jieba is not None:
        jieba.add_word(term)

_model: Any | None = None
_index: Any | None = None
_bm25_index: Any | None = None
_chunks_cache: list[dict[str, Any]] = []
_tokenized_corpus_cache: list[list[str]] = []
_manuals_signature: tuple[tuple[str, float, int], ...] = ()


def get_model() -> Any:
    global _model
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers 不可用")
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def generate_embeddings(chunks: list[dict[str, Any]]) -> Any:
    if np is None:
        return []

    texts = [str(chunk.get("content", "")) for chunk in chunks]
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    embeddings = get_model().encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return embeddings.astype(np.float32)


def build_faiss_index(chunks: list[dict[str, Any]]) -> faiss.IndexFlatL2:
    if faiss is None or np is None or SentenceTransformer is None:
        return None

    embeddings = generate_embeddings(chunks)
    if embeddings.size == 0:
        return faiss.IndexFlatL2(1)

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index


def build_bm25_index(chunks: list[dict[str, Any]]) -> BM25Okapi | None:
    if BM25Okapi is None:
        return None

    tokenized_corpus = [tokenize_text(str(chunk.get("content", ""))) for chunk in chunks]
    if not tokenized_corpus:
        return None

    return BM25Okapi(tokenized_corpus)


def tokenize_text(text: str) -> list[str]:
    if jieba is None:
        return re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_/-]+", text.lower())

    tokens = jieba.lcut(text.lower())
    return [token.strip() for token in tokens if token.strip()]


def semantic_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    keyword = query.strip()
    if not keyword:
        return []

    chunks, index = get_cached_index()
    if not chunks or index is None or getattr(index, "ntotal", 0) == 0 or np is None:
        return []

    query_embedding = get_model().encode(
        [keyword],
        convert_to_numpy=True,
        show_progress_bar=False,
    ).astype(np.float32)

    limit = min(top_k, len(chunks))
    distances, indices = index.search(query_embedding, limit)

    results: list[dict[str, Any]] = []
    for distance, chunk_index in zip(distances[0], indices[0], strict=False):
        if chunk_index < 0:
            continue

        chunk = dict(chunks[int(chunk_index)])
        chunk["score"] = float(distance)
        results.append(chunk)

    return results


def keyword_search(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    keyword = query.strip().lower()
    if not keyword:
        return []

    chunks, _index, _bm25_index = get_cached_indexes()
    query_tokens = get_query_tokens(keyword)
    if not chunks or not query_tokens:
        return []

    results: list[dict[str, Any]] = []
    for chunk in chunks:
        content = str(chunk.get("content", ""))
        lower_content = content.lower()
        keyword_hits = count_keyword_hits(keyword, query_tokens, lower_content)
        if keyword_hits <= 0:
            continue

        keyword_boost = calculate_keyword_boost(keyword, query_tokens, lower_content)
        results.append(
            {
                **chunk,
                "keyword_hits": keyword_hits,
                "keyword_boost": keyword_boost,
            }
        )

    results.sort(
        key=lambda item: (
            float(item["keyword_boost"]),
            int(item["keyword_hits"]),
        ),
        reverse=True,
    )
    return results[:top_k]


def bm25_search(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    keyword = query.strip()
    if not keyword:
        return []

    chunks, _index, bm25_index = get_cached_indexes()
    query_tokens = get_query_tokens(keyword)
    if not chunks or bm25_index is None or not query_tokens:
        return []

    scores = bm25_index.get_scores(query_tokens)
    if np is not None:
        ranked_indices = np.argsort(scores)[::-1][: min(top_k, len(chunks))]
    else:
        ranked_indices = [
            index
            for index, _score in sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[
                : min(top_k, len(chunks))
            ]
        ]

    results: list[dict[str, Any]] = []
    for chunk_index in ranked_indices:
        score = float(scores[int(chunk_index)])
        if score <= 0:
            continue

        results.append(
            {
                **chunks[int(chunk_index)],
                "bm25_score": score,
            }
        )

    return results


def hybrid_search(query: str, top_k: int = 5, device_model: str | None = None) -> list[dict[str, Any]]:
    normalized_device_model = normalize_device_model(device_model)
    if RAG_BACKEND.lower() == "langchain":
        try:
            from backend.rag.rag_chain import generate_rag_contexts_with_info

            filters = {"device_model": normalized_device_model} if normalized_device_model else None
            contexts, _filter_info = generate_rag_contexts_with_info(query, top_k=top_k, filters=filters)
            if contexts:
                return contexts
            print("[LangChain RAG] fallback to legacy search")
        except Exception as exc:
            print(f"[LangChain RAG] unavailable, fallback to legacy search. reason: {exc}")

    return legacy_hybrid_search(query, top_k=top_k, device_model=normalized_device_model)


def legacy_hybrid_search(query: str, top_k: int = 5, device_model: str | None = None) -> list[dict[str, Any]]:
    keyword = query.strip()
    if not keyword:
        return []

    candidate_limit = max(top_k * 5, 20)
    keyword_results = keyword_search(keyword, top_k=candidate_limit)
    bm25_results = bm25_search(keyword, top_k=candidate_limit)
    semantic_results = semantic_search(keyword, top_k=candidate_limit)

    merged: dict[str, dict[str, Any]] = {}

    for item in keyword_results:
        chunk_id = get_chunk_id(item)
        merged[chunk_id] = {
            **item,
            "semantic_score": 0.0,
            "bm25_score": 0.0,
            "keyword_hits": int(item.get("keyword_hits", 0)),
            "keyword_boost": float(item.get("keyword_boost", 0.0)),
        }

    for item in bm25_results:
        chunk_id = get_chunk_id(item)
        current = merged.setdefault(
            chunk_id,
            {
                **item,
                "semantic_score": 0.0,
                "bm25_score": 0.0,
                "keyword_hits": 0,
                "keyword_boost": 0.0,
            },
        )
        current["bm25_score"] = max(float(current.get("bm25_score", 0.0)), float(item["bm25_score"]))

    for item in semantic_results:
        chunk_id = get_chunk_id(item)
        semantic_distance = float(item.get("score", 0.0))
        current = merged.setdefault(
            chunk_id,
            {
                **item,
                "semantic_score": semantic_distance,
                "bm25_score": 0.0,
                "keyword_hits": 0,
                "keyword_boost": 0.0,
            },
        )
        current["semantic_score"] = semantic_distance

    query_tokens = get_query_tokens(keyword)
    for item in merged.values():
        content = str(item.get("content", "")).lower()
        if int(item.get("keyword_hits", 0)) == 0:
            item["keyword_hits"] = count_keyword_hits(keyword.lower(), query_tokens, content)
        if float(item.get("keyword_boost", 0.0)) == 0:
            item["keyword_boost"] = calculate_keyword_boost(keyword.lower(), query_tokens, content)

        semantic_distance = float(item.get("semantic_score", 0.0))
        final_score = (
            float(item.get("keyword_boost", 0.0))
            + float(item.get("bm25_score", 0.0))
            - semantic_distance
        )
        item["final_score"] = round(final_score, 4)
        item["semantic_score"] = round(semantic_distance, 4)
        item["bm25_score"] = round(float(item.get("bm25_score", 0.0)), 4)

        item.pop("score", None)
        item.pop("keyword_boost", None)

    ranked_results = sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("final_score", 0.0)),
            int(item.get("keyword_hits", 0)),
            float(item.get("bm25_score", 0.0)),
        ),
        reverse=True,
    )
    normalized_device_model = normalize_device_model(device_model)
    if not normalized_device_model:
        return add_filter_metadata(ranked_results[:top_k], False, False, "", "")

    filtered_results = [
        item for item in ranked_results if normalize_device_model(item.get("device_model")) == normalized_device_model
    ]
    if filtered_results:
        return add_filter_metadata(
            filtered_results[:top_k],
            True,
            False,
            f"已优先使用设备型号 {normalized_device_model} 的知识来源",
            normalized_device_model,
        )

    return add_filter_metadata(
        ranked_results[:top_k],
        True,
        True,
        "当前设备型号下依据不足，已扩展到全库检索",
        normalized_device_model,
    )


def add_filter_metadata(
    results: list[dict[str, Any]],
    used_device_filter: bool,
    filter_fallback: bool,
    filter_message: str,
    requested_device_model: str,
) -> list[dict[str, Any]]:
    for item in results:
        item["used_device_filter"] = used_device_filter
        item["filter_fallback"] = filter_fallback
        item["filter_message"] = filter_message
        item["requested_device_model"] = requested_device_model
    return results


def get_cached_index() -> tuple[list[dict[str, Any]], Any]:
    chunks, index, _bm25_index = get_cached_indexes()
    return chunks, index


def get_cached_indexes() -> tuple[list[dict[str, Any]], Any, Any | None]:
    global _chunks_cache, _index, _manuals_signature
    global _bm25_index, _tokenized_corpus_cache

    current_signature = get_manuals_signature()
    if _index is None or current_signature != _manuals_signature:
        _chunks_cache = load_manual_chunks()
        _index = build_faiss_index(_chunks_cache)
        _tokenized_corpus_cache = [
            tokenize_text(str(chunk.get("content", ""))) for chunk in _chunks_cache
        ]
        _bm25_index = BM25Okapi(_tokenized_corpus_cache) if BM25Okapi is not None and _tokenized_corpus_cache else None
        _manuals_signature = current_signature

    return _chunks_cache, _index, _bm25_index


def get_query_tokens(query: str) -> list[str]:
    tokens = tokenize_text(query)
    return [token for token in tokens if len(token) > 1 or token.isalnum()]


def count_keyword_hits(query: str, query_tokens: list[str], content: str) -> int:
    hits = 0
    if query and query in content:
        hits += len(query_tokens) + 2

    hits += sum(1 for token in query_tokens if token in content)
    return hits


def calculate_keyword_boost(query: str, query_tokens: list[str], content: str) -> float:
    if not query_tokens:
        return 0.0

    boost = 0.0
    if query in content:
        boost += 8.0

    reversed_phrase = "".join(reversed(query_tokens))
    if len(query_tokens) > 1 and reversed_phrase in content:
        boost += 5.0

    token_hits = sum(1 for token in query_tokens if token in content)
    boost += token_hits * 1.8

    action_hits = sum(1 for token in query_tokens if token in INDUSTRIAL_ACTION_TERMS and token in content)
    part_hits = sum(1 for token in query_tokens if token in INDUSTRIAL_PART_TERMS and token in content)
    boost += action_hits * 2.5
    boost += part_hits * 2.0

    if action_hits and part_hits:
        boost += 4.0

    query_has_action = any(token in INDUSTRIAL_ACTION_TERMS for token in query_tokens)
    content_action_hits = sum(1 for term in INDUSTRIAL_ACTION_TERMS if term in content)
    if query_has_action and content_action_hits:
        boost += min(content_action_hits, 2) * 1.5

    if contains_step_or_parameter_text(content):
        boost += 2.0

    if token_hits >= 2:
        boost += token_hits

    return boost


def contains_step_or_parameter_text(content: str) -> bool:
    if any(marker in content for marker in STEP_MARKERS):
        return True

    return any(unit in content for unit in ("n·m", "nm", "mm", "毫米", "扭矩", "间隙"))


def get_chunk_id(chunk: dict[str, Any]) -> str:
    chunk_id = chunk.get("chunk_id")
    if chunk_id:
        return str(chunk_id)

    return f"{chunk.get('filename', 'manual')}-{chunk.get('page', 0)}-{hash(chunk.get('content', ''))}"


def get_manuals_signature() -> tuple[tuple[str, float, int], ...]:
    signature: list[tuple[str, float, int]] = []
    for source_dir, directory in MANUAL_DIRS:
        if not directory.exists():
            continue
        for pdf_path in sorted(directory.glob("*.pdf")):
            stat = Path(pdf_path).stat()
            signature.append((f"{source_dir}:{pdf_path.name}", stat.st_mtime, stat.st_size))
    return tuple(signature)
