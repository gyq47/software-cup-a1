from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.evidence_service import build_grounding_result, build_retrieval_filter_result
from backend.services.tool_orchestrator_service import run_workflow_pipeline_trace
from backend.services.workflow_service import generate_workflow_card

router = APIRouter(prefix="/workflow", tags=["workflow"])


class WorkflowRequest(BaseModel):
    task: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    device_model: str | None = None


class WorkflowResponse(BaseModel):
    task: str
    workflow: dict[str, Any]
    compliance_result: dict[str, Any]
    contexts: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    grounding_result: dict[str, Any]
    retrieval_filter: dict[str, Any]
    graph_context: dict[str, Any] = Field(default_factory=dict)
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    seed_nodes: list[dict[str, Any]] = Field(default_factory=list)
    graph_enabled: bool = False
    graph_warnings: list[str] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/generate")
def generate_workflow(request: WorkflowRequest) -> WorkflowResponse:
    try:
        workflow, compliance_result, contexts, evidence_items, graph_context = generate_workflow_card(
            request.task,
            top_k=request.top_k,
            device_model=request.device_model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="标准化作业卡生成失败") from exc

    retrieval_filter = build_retrieval_filter_result(contexts)
    return WorkflowResponse(
        task=request.task,
        workflow=workflow,
        compliance_result=compliance_result,
        contexts=contexts,
        evidence_items=evidence_items,
        grounding_result=build_grounding_result(contexts),
        retrieval_filter=retrieval_filter,
        graph_context=graph_context,
        graph_paths=graph_context.get("paths", []),
        seed_nodes=graph_context.get("seed_nodes", []),
        graph_enabled=bool(graph_context.get("enabled", False)),
        graph_warnings=graph_context.get("warnings", []),
        tool_trace=run_workflow_pipeline_trace(
            request.task,
            contexts,
            retrieval_filter,
            graph_context,
            workflow,
            compliance_result,
        ),
    )
