from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.services.pdf_service import MANUAL_UPLOAD_DIR, load_manual_chunks

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_model: SentenceTransformer | None = None
_index: faiss.IndexFlatL2 | None = None
_chunks_cache: list[dict[str, Any]] = []
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


def get_cached_index() -> tuple[list[dict[str, Any]], faiss.IndexFlatL2]:
    global _chunks_cache, _index, _manuals_signature

    current_signature = get_manuals_signature()
    if _index is None or current_signature != _manuals_signature:
        _chunks_cache = load_manual_chunks()
        _index = build_faiss_index(_chunks_cache)
        _manuals_signature = current_signature

    return _chunks_cache, _index


def get_manuals_signature() -> tuple[tuple[str, float, int], ...]:
    if not MANUAL_UPLOAD_DIR.exists():
        return ()

    signature: list[tuple[str, float, int]] = []
    for pdf_path in sorted(MANUAL_UPLOAD_DIR.glob("*.pdf")):
        stat = Path(pdf_path).stat()
        signature.append((pdf_path.name, stat.st_mtime, stat.st_size))
    return tuple(signature)
