from typing import Any

from fastapi import APIRouter, Query

from backend.services.pdf_service import search_manual_chunks
from backend.services.vector_service import hybrid_search, semantic_search

router = APIRouter(prefix="/manual", tags=["manual"])


@router.get("/search")
def search_manual(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    matches = search_manual_chunks(q)
    return {
        "query": q,
        "results": matches,
    }


@router.get("/semantic-search")
def semantic_search_manual(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
) -> dict[str, Any]:
    matches = semantic_search(q, top_k=top_k)
    return {
        "query": q,
        "results": matches,
    }


@router.get("/hybrid-search")
def hybrid_search_manual(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
) -> dict[str, Any]:
    matches = hybrid_search(q, top_k=top_k)
    return {
        "query": q,
        "results": matches,
    }
