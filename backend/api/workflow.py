from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.workflow_service import generate_workflow_card

router = APIRouter(prefix="/workflow", tags=["workflow"])


class WorkflowRequest(BaseModel):
    task: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class WorkflowResponse(BaseModel):
    task: str
    workflow: dict[str, Any]
    compliance_result: dict[str, Any]
    contexts: list[dict[str, Any]]


@router.post("/generate")
def generate_workflow(request: WorkflowRequest) -> WorkflowResponse:
    try:
        workflow, compliance_result, contexts = generate_workflow_card(
            request.task,
            top_k=request.top_k,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="标准化作业卡生成失败") from exc

    return WorkflowResponse(
        task=request.task,
        workflow=workflow,
        compliance_result=compliance_result,
        contexts=contexts,
    )
