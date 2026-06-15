from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from backend.core.config import DISABLE_CHROMA, VECTOR_STORE_DIR, VECTOR_STORE_PATH
from backend.rag.embeddings import create_embeddings

_vector_store: Optional[Any] = None


class ChromaDocument:
    def __init__(self, page_content: str, metadata: Optional[dict[str, Any]] = None) -> None:
        self.page_content = page_content
        self.metadata = metadata or {}


class ChromaCollectionAdapter:
    def __init__(self, collection: Any) -> None:
        self.collection = collection

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[tuple[ChromaDocument, float]]:
        include = ["documents", "metadatas", "distances"]
        query_kwargs = {"query_texts": [query], "n_results": k, "include": include}
        if filter:
            query_kwargs["where"] = filter
        result = self.collection.query(**query_kwargs)
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        matches: list[tuple[ChromaDocument, float]] = []
        for content, metadata, distance in zip(documents, metadatas, distances):
            matches.append((ChromaDocument(str(content or ""), dict(metadata or {})), float(distance or 0.0)))
        return matches

    def add_documents(self, documents: list[Any]) -> None:
        ids: list[str] = []
        contents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for document in documents:
            content = str(getattr(document, "page_content", "") or "")
            if not content.strip():
                continue
            metadata = sanitize_metadata(getattr(document, "metadata", {}) or {})
            chunk_id = str(metadata.get("chunk_id") or uuid4())
            metadata["chunk_id"] = chunk_id
            ids.append(chunk_id)
            contents.append(content)
            metadatas.append(metadata)
        if ids:
            self.collection.add(ids=ids, documents=contents, metadatas=metadatas)

    def delete(self, where: dict[str, Any]) -> None:
        self.collection.delete(where=where)

    def persist(self) -> None:
        return None


def get_vector_store() -> Optional[Any]:
    global _vector_store
    if DISABLE_CHROMA:
        print("[LangChain RAG] Chroma disabled, fallback to legacy search.")
        return None

    if _vector_store is not None:
        return _vector_store

    embeddings = create_embeddings()
    if embeddings is None:
        _vector_store = get_chromadb_vector_store()
        return _vector_store

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
        _vector_store = get_chromadb_vector_store()
        return _vector_store


def get_chromadb_vector_store() -> Optional[ChromaCollectionAdapter]:
    try:
        import chromadb

        VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
        collection = client.get_or_create_collection(name="manual_knowledge")
        print("[Chroma RAG] vector store ready")
        return ChromaCollectionAdapter(collection)
    except Exception as exc:
        print(f"[Chroma RAG] unavailable, fallback to legacy search. reason: {exc}")
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


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        elif isinstance(value, Path):
            sanitized[key] = str(value)
        else:
            sanitized[key] = str(value)
    return sanitized
