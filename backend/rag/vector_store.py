from pathlib import Path
from typing import Any

from backend.core.config import DISABLE_CHROMA, VECTOR_STORE_DIR, VECTOR_STORE_PATH
from backend.rag.embeddings import create_embeddings

_vector_store: Any | None = None


def get_vector_store() -> Any | None:
    global _vector_store
    if DISABLE_CHROMA:
        print("[LangChain RAG] Chroma disabled, fallback to legacy search.")
        return None

    if _vector_store is not None:
        return _vector_store

    embeddings = create_embeddings()
    if embeddings is None:
        return None

    try:
        from langchain_community.vectorstores import Chroma

        VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
        _vector_store = Chroma(
            persist_directory=str(VECTOR_STORE_PATH),
            embedding_function=embeddings,
            collection_name="manual_knowledge",
        )
        print("[LangChain RAG] vector store ready")
        return _vector_store
    except Exception as exc:
        print(f"[LangChain RAG] unavailable, fallback to legacy search. reason: {exc}")
        _vector_store = None
        return None


def add_documents_to_vector_store(documents: list[Any]) -> bool:
    if not documents:
        return False

    vector_store = get_vector_store()
    if vector_store is None:
        return False

    try:
        vector_store.add_documents(documents)
        if hasattr(vector_store, "persist"):
            vector_store.persist()
        print("[LangChain RAG] vector store ready")
        return True
    except Exception as exc:
        print(f"[LangChain RAG] fallback to legacy search. reason: {exc}")
        return False


def reset_vector_store_cache() -> None:
    global _vector_store
    _vector_store = None
