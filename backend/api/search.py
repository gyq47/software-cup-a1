from typing import Any

from fastapi import APIRouter, Query

from backend.services.pdf_service import search_manual_chunks

router = APIRouter(prefix="/manual", tags=["manual"])


@router.get("/search")
def search_manual(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    matches = search_manual_chunks(q)
    return {
        "query": q,
        "results": matches,
    }
