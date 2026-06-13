import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from backend.core.config import MANUAL_STATIC_PATH, MANUAL_UPLOAD_PATH
from backend.rag.metadata_service import extract_document_metadata

DEFAULT_CHUNK_SIZE = 500
MANUAL_UPLOAD_DIR = MANUAL_UPLOAD_PATH
MANUAL_STATIC_DIR = MANUAL_STATIC_PATH
PROCESSED_MANUAL_CHUNKS_PATH = Path("backend/data/processed/manual_text_chunks_test_v2.jsonl").resolve()
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
    processed_chunks = load_processed_manual_chunks()
    if processed_chunks:
        return processed_chunks

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


def load_processed_manual_chunks() -> list[dict[str, Any]]:
    if not PROCESSED_MANUAL_CHUNKS_PATH.exists():
        return []

    chunks: list[dict[str, Any]] = []
    try:
        with PROCESSED_MANUAL_CHUNKS_PATH.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                metadata = item.get("metadata") or {}
                content = str(item.get("content") or "")
                if not content:
                    continue
                page_number = metadata.get("page_number") or metadata.get("page") or ""
                chunks.append(
                    {
                        "content": content,
                        "page": page_number,
                        "page_number": page_number,
                        "chunk_id": metadata.get("chunk_id", ""),
                        "filename": metadata.get("pdf_filename", ""),
                        "pdf_filename": metadata.get("pdf_filename", ""),
                        "device_model": metadata.get("device_model", ""),
                        "manual_type": metadata.get("manual_type", ""),
                        "source_type": metadata.get("source_type", "manual_text"),
                        "source_dir": metadata.get("source_dir", "processed"),
                        "relative_path": metadata.get("relative_path", ""),
                        "section_title": metadata.get("section_title", ""),
                        "text_hash": metadata.get("text_hash", ""),
                    }
                )
    except Exception as exc:
        print(f"[PDF fallback] processed chunks unavailable, fallback to PDF parsing. reason: {exc}")
        return []

    return chunks


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
