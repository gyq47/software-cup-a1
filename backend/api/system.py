from typing import Any

from fastapi import APIRouter, Query

from backend.services.system_diagnostics_service import run_system_diagnostics, run_system_health

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def system_health() -> dict[str, Any]:
    return run_system_health()


@router.get("/diagnostics")
def system_diagnostics(deep_check: bool = Query(default=False)) -> dict[str, Any]:
    return run_system_diagnostics(deep_check=deep_check)
