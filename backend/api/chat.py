import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.evidence_service import build_evidence_items
from backend.services.evidence_service import build_grounding_result
from backend.services.evidence_service import build_retrieval_filter_result
from backend.services.lazy_graphrag_service import build_lazy_graph_context
from backend.services.llm_service import generate_repair_answer
from backend.services.tool_orchestrator_service import run_chat_pipeline_trace
from backend.services.vector_service import hybrid_search

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    device_model: str | None = None


class ChatResponse(BaseModel):
    question: str
    answer: str
    structured_answer: dict[str, Any] | None = None
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


@router.post("")
def chat(request: ChatRequest) -> ChatResponse:
    try:
        try:
            from backend.rag.rag_chain import generate_rag_answer_with_graph_info

            filters = {"device_model": request.device_model} if request.device_model else None
            answer, contexts, _filter_info, graph_context = generate_rag_answer_with_graph_info(
                request.question,
                top_k=request.top_k,
                filters=filters,
            )
        except Exception as exc:
            print(f"[LangChain RAG] fallback to legacy search. reason: {exc}")
            contexts = []
            answer = ""
            graph_context = {}

        if not contexts:
            contexts = hybrid_search(request.question, top_k=request.top_k, device_model=request.device_model)
            graph_context = build_lazy_graph_context(request.question, contexts, device_model=request.device_model)
            answer = generate_repair_answer(request.question, contexts)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="问答服务处理失败") from exc

    retrieval_filter = build_retrieval_filter_result(contexts)
    return ChatResponse(
        question=request.question,
        answer=answer,
        structured_answer=parse_structured_answer(answer),
        contexts=contexts,
        evidence_items=build_evidence_items(contexts),
        grounding_result=build_grounding_result(contexts),
        retrieval_filter=retrieval_filter,
        graph_context=graph_context,
        graph_paths=graph_context.get("paths", []),
        seed_nodes=graph_context.get("seed_nodes", []),
        graph_enabled=bool(graph_context.get("enabled", False)),
        graph_warnings=graph_context.get("warnings", []),
        tool_trace=run_chat_pipeline_trace(request.question, contexts, retrieval_filter, graph_context),
    )


def parse_structured_answer(answer: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
