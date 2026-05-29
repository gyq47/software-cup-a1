from typing import Any

from backend.core.config import CHUNK_OVERLAP, CHUNK_SIZE


def split_documents(
    documents: list[Any],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Any]:
    if not documents:
        return []

    print("[LangChain RAG] splitting documents")
    try:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except Exception:
            from langchain.text_splitter import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "；", ";", "，", ",", " ", ""],
        )
        chunks = splitter.split_documents(documents)
    except Exception as exc:
        print(f"[LangChain RAG] splitter unavailable, fallback reason: {exc}")
        chunks = documents

    for index, document in enumerate(chunks, start=1):
        filename = document.metadata.get("filename", "manual")
        page = document.metadata.get("page", 0)
        document.metadata["chunk_id"] = document.metadata.get("chunk_id") or f"{filename}-p{page}-{index}"
    return chunks
