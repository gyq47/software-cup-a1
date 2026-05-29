from pathlib import Path
from typing import Any

from pypdf import PdfReader

from backend.core.config import MANUAL_STATIC_PATH, MANUAL_UPLOAD_PATH
from backend.rag.metadata_service import extract_document_metadata

DEFAULT_CHUNK_SIZE = 500
MANUAL_UPLOAD_DIR = MANUAL_UPLOAD_PATH
MANUAL_STATIC_DIR = MANUAL_STATIC_PATH
MANUAL_DIRS = (
    ("upload", MANUAL_UPLOAD_DIR),
    ("static", MANUAL_STATIC_DIR),
)


def extract_pdf_chunks(
    pdf_path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[dict[str, Any]]:
    reader = PdfReader(pdf_path)
    chunks: list[dict[str, Any]] = []

    for page_index, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if not text:
            continue

        for start in range(0, len(text), chunk_size):
            content = text[start : start + chunk_size]
            chunks.append(
                {
                    "content": content,
                    "page": page_index,
                    "chunk_id": f"{pdf_path.stem}-p{page_index}-{len(chunks) + 1}",
                }
            )

    return chunks


def load_manual_chunks(chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[dict[str, Any]]:
    all_chunks: list[dict[str, Any]] = []
    for source_dir, directory in MANUAL_DIRS:
        if not directory.exists():
            continue
        for pdf_path in sorted(directory.rglob("*.pdf")):
            metadata = extract_document_metadata(pdf_path, {"source_dir": source_dir})
            for chunk in extract_pdf_chunks(pdf_path, chunk_size=chunk_size):
                all_chunks.append(
                    {
                        **chunk,
                        "filename": pdf_path.name,
                        "device_model": metadata.get("device_model", ""),
                        "manual_type": metadata.get("manual_type", ""),
                        "source_dir": source_dir,
                        "relative_path": metadata.get("relative_path", ""),
                    }
                )

    return all_chunks


def search_manual_chunks(query: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[dict[str, Any]]:
    keyword = query.strip().lower()
    if not keyword:
        return []

    matched_chunks: list[dict[str, Any]] = []
    for chunk in load_manual_chunks(chunk_size=chunk_size):
        content = str(chunk["content"])
        if keyword in content.lower():
            matched_chunks.append(chunk)

    return matched_chunks


def normalize_text(text: str) -> str:
    return " ".join(text.split())
