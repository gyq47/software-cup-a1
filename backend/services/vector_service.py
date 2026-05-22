from pathlib import Path
from typing import Any

import faiss
import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from backend.services.pdf_service import MANUAL_UPLOAD_DIR, load_manual_chunks

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
    jieba.add_word(term)

_model: SentenceTransformer | None = None
_index: faiss.IndexFlatL2 | None = None
_bm25_index: BM25Okapi | None = None
_chunks_cache: list[dict[str, Any]] = []
_tokenized_corpus_cache: list[list[str]] = []
_manuals_signature: tuple[tuple[str, float, int], ...] = ()


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def generate_embeddings(chunks: list[dict[str, Any]]) -> np.ndarray:
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
    embeddings = generate_embeddings(chunks)
    if embeddings.size == 0:
        return faiss.IndexFlatL2(1)

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index


def build_bm25_index(chunks: list[dict[str, Any]]) -> BM25Okapi | None:
    tokenized_corpus = [tokenize_text(str(chunk.get("content", ""))) for chunk in chunks]
    if not tokenized_corpus:
        return None

    return BM25Okapi(tokenized_corpus)


def tokenize_text(text: str) -> list[str]:
    tokens = jieba.lcut(text.lower())
    return [token.strip() for token in tokens if token.strip()]


def semantic_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    keyword = query.strip()
    if not keyword:
        return []

    chunks, index = get_cached_index()
    if not chunks or index.ntotal == 0:
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
    ranked_indices = np.argsort(scores)[::-1][: min(top_k, len(chunks))]

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


def hybrid_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
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
    return ranked_results[:top_k]


def get_cached_index() -> tuple[list[dict[str, Any]], faiss.IndexFlatL2]:
    chunks, index, _bm25_index = get_cached_indexes()
    return chunks, index


def get_cached_indexes() -> tuple[list[dict[str, Any]], faiss.IndexFlatL2, BM25Okapi | None]:
    global _chunks_cache, _index, _manuals_signature
    global _bm25_index, _tokenized_corpus_cache

    current_signature = get_manuals_signature()
    if _index is None or current_signature != _manuals_signature:
        _chunks_cache = load_manual_chunks()
        _index = build_faiss_index(_chunks_cache)
        _tokenized_corpus_cache = [
            tokenize_text(str(chunk.get("content", ""))) for chunk in _chunks_cache
        ]
        _bm25_index = BM25Okapi(_tokenized_corpus_cache) if _tokenized_corpus_cache else None
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
    if not MANUAL_UPLOAD_DIR.exists():
        return ()

    signature: list[tuple[str, float, int]] = []
    for pdf_path in sorted(MANUAL_UPLOAD_DIR.glob("*.pdf")):
        stat = Path(pdf_path).stat()
        signature.append((pdf_path.name, stat.st_mtime, stat.st_size))
    return tuple(signature)
