from typing import Any

from backend.core.config import EMBEDDING_MODEL_NAME


def create_embeddings() -> Any | None:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        print("[LangChain RAG] embedding documents")
        return HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception as exc:
        print(f"[LangChain RAG] unavailable, fallback to legacy search. reason: {exc}")
        return None
