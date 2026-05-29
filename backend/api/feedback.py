from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.feedback_service import (
    get_cases,
    get_pending_feedback,
    review_feedback,
    submit_feedback,
)
from backend.services.tool_orchestrator_service import run_feedback_pipeline_trace

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackSubmitRequest(BaseModel):
    source_type: str = Field(...)
    source_id: str = ""
    original_question: str = ""
    original_answer: str = ""
    correction_type: str = "other"
    correction_text: str = Field(..., min_length=1)
    related_device: str = ""
    related_fault: str = ""
    submitter_role: str = "worker"
    priority: str = "medium"


class FeedbackReviewRequest(BaseModel):
    feedback_id: str = Field(..., min_length=1)
    action: str = Field(...)
    review_comment: str = ""
    reviewer: str = "expert"


@router.post("/submit")
def submit(request: FeedbackSubmitRequest) -> dict[str, Any]:
    try:
        return submit_feedback(request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail="反馈提交失败") from exc


@router.get("/pending")
def pending() -> dict[str, list[dict[str, Any]]]:
    return get_pending_feedback()


@router.post("/review")
def review(request: FeedbackReviewRequest) -> dict[str, Any]:
    try:
        result = review_feedback(request.model_dump())
        if result.get("status") == "approved":
            result["tool_trace"] = run_feedback_pipeline_trace(result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="反馈审核失败") from exc


@router.get("/cases")
def cases() -> dict[str, list[dict[str, Any]]]:
    return get_cases()
