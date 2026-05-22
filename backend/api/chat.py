from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.llm_service import generate_repair_answer
from backend.services.vector_service import semantic_search

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class ChatResponse(BaseModel):
    question: str
    answer: str
    contexts: list[dict[str, Any]]


@router.post("")
def chat(request: ChatRequest) -> ChatResponse:
    try:
        contexts = semantic_search(request.question, top_k=request.top_k)
        answer = generate_repair_answer(request.question, contexts)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="问答服务处理失败") from exc

    return ChatResponse(
        question=request.question,
        answer=answer,
        contexts=contexts,
    )
