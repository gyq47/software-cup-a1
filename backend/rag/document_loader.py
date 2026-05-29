from pathlib import Path
from typing import Any

from backend.rag.metadata_service import extract_document_metadata


def load_documents(file_path: str | Path, metadata: dict[str, Any] | None = None) -> list[Any]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    base_metadata = extract_document_metadata(path, metadata)

    print("[LangChain RAG] loading documents")
    try:
        if suffix == ".pdf":
            return load_pdf_documents(path, base_metadata)
        if suffix in {".txt", ".md"}:
            return load_text_documents(path, base_metadata)
    except Exception as exc:
        print(f"[LangChain RAG] loader unavailable, fallback reason: {exc}")
        return []

    return []


def load_pdf_documents(path: Path, metadata: dict[str, Any]) -> list[Any]:
    try:
        from langchain_community.document_loaders import PyPDFLoader

        documents = PyPDFLoader(str(path)).load()
        for document in documents:
            page = int(document.metadata.get("page", 0)) + 1
            document.metadata.update({**metadata, "page": page})
        return documents
    except Exception:
        return load_pdf_documents_with_pypdf(path, metadata)


def load_pdf_documents_with_pypdf(path: Path, metadata: dict[str, Any]) -> list[Any]:
    from langchain_core.documents import Document
    from pypdf import PdfReader

    reader = PdfReader(path)
    documents: list[Any] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = " ".join((page.extract_text() or "").split())
        if text:
            documents.append(
                Document(
                    page_content=text,
                    metadata={**metadata, "page": page_index},
                )
            )
    return documents


def load_text_documents(path: Path, metadata: dict[str, Any]) -> list[Any]:
    from langchain_core.documents import Document

    content = path.read_text(encoding="utf-8")
    return [Document(page_content=content, metadata={**metadata, "page": 1})]
