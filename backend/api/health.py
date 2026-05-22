from fastapi import APIRouter

from backend.core.config import VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "backend",
        "version": VERSION,
    }
