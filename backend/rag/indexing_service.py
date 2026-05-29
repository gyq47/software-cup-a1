import shutil
from pathlib import Path
from typing import Any

from backend.core.config import (
    IMAGE_KNOWLEDGE_MAX_PAGES,
    MANUAL_STATIC_PATH,
    MANUAL_UPLOAD_PATH,
    VECTOR_STORE_DIR,
    VECTOR_STORE_PATH,
)
from backend.rag.document_loader import load_documents
from backend.rag.metadata_service import extract_document_metadata
from backend.rag.text_splitter import split_documents
from backend.rag.vector_store import add_documents_to_vector_store, get_vector_store, reset_vector_store_cache
from backend.services.case_indexing_service import index_existing_feedback_cases
from backend.services.pdf_image_knowledge_service import build_page_image_documents
from backend.services.pdf_page_image_service import ensure_pdf_page_images
from backend.services.pdf_service import extract_pdf_chunks

SUPPORTED_MANUAL_SUFFIXES = {".pdf", ".txt", ".md"}
MANUAL_DIRS = (
    ("upload", MANUAL_UPLOAD_PATH),
    ("static", MANUAL_STATIC_PATH),
)


def index_document(
    file_path: str | Path,
    metadata: dict[str, Any] | None = None,
    max_image_pages: int | None = None,
) -> dict[str, Any]:
    path = Path(file_path)
    document_metadata = extract_document_metadata(path, build_metadata(path, metadata))
    documents = load_documents(path, document_metadata)
    page_images = ensure_pdf_page_images(path, document_metadata)
    chunks = split_documents(documents)
    enrich_chunks_with_page_images(chunks, path, document_metadata, page_images)
    image_documents = build_page_image_documents(
        path,
        document_metadata,
        page_images,
        max_pages=IMAGE_KNOWLEDGE_MAX_PAGES if max_image_pages is None else max_image_pages,
    )
    image_pages_processed = min(
        IMAGE_KNOWLEDGE_MAX_PAGES if max_image_pages is None else max(max_image_pages, 0),
        len(page_images),
    )
    all_chunks = [*chunks, *image_documents]
    chunk_count = len(all_chunks) if all_chunks else count_fallback_chunks(path)
    indexed = add_documents_to_vector_store(all_chunks)
    return {
        "indexed": indexed,
        "chunks": chunk_count,
        "text_chunks": len(chunks),
        "image_knowledge_chunks": len(image_documents),
        "image_knowledge_pages_processed": image_pages_processed,
        "metadata": document_metadata,
        "message": "LangChain 向量索引已建立" if indexed else "LangChain 索引不可用，已保留旧检索兼容模式",
    }


def enrich_chunks_with_page_images(
    chunks: list[Any],
    path: Path,
    document_metadata: dict[str, Any],
    page_images: dict[int, str],
) -> None:
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {}) or {}
        page_number = normalize_page_number(metadata.get("page"))
        metadata["page_number"] = page_number
        metadata["pdf_filename"] = path.name if path.suffix.lower() == ".pdf" else ""
        metadata["source"] = metadata.get("source") or document_metadata.get("source") or str(path)
        metadata["device_model"] = metadata.get("device_model") or document_metadata.get("device_model", "")
        metadata["manual_type"] = metadata.get("manual_type") or document_metadata.get("manual_type", "")
        metadata["doc_type"] = metadata.get("doc_type") or document_metadata.get("doc_type", metadata.get("manual_type", ""))
        metadata["source_type"] = metadata.get("source_type") or "manual_text"
        metadata["page_image_path"] = page_images.get(page_number, "")
        chunk.metadata = metadata


def normalize_page_number(value: Any) -> int:
    try:
        page_number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(page_number, 0)


def rebuild_index() -> dict[str, Any]:
    clear_vector_store()

    total_chunks = 0
    indexed_files = 0
    failed_files: list[dict[str, str]] = []
    manual_paths = sort_manual_paths_for_image_knowledge(get_all_manual_paths())
    remaining_image_pages = IMAGE_KNOWLEDGE_MAX_PAGES

    for manual_path in manual_paths:
        result = index_document(manual_path, max_image_pages=remaining_image_pages)
        remaining_image_pages = max(remaining_image_pages - int(result.get("image_knowledge_pages_processed", 0)), 0)
        if result.get("indexed"):
            indexed_files += 1
        else:
            failed_files.append(
                {
                    "filename": manual_path.name,
                    "reason": str(result.get("message", "索引失败")),
                }
            )
        total_chunks += int(result.get("chunks", 0))

    case_index_result = index_existing_feedback_cases()

    return {
        "success": indexed_files > 0,
        "total_files": len(manual_paths),
        "indexed_files": indexed_files,
        "failed_files": failed_files,
        "total_chunks": total_chunks,
        "image_knowledge_chunks": IMAGE_KNOWLEDGE_MAX_PAGES - remaining_image_pages,
        "feedback_case_count": int(case_index_result.get("case_count", 0)),
        "feedback_case_indexed": bool(case_index_result.get("indexed", False)),
        "vector_store_dir": VECTOR_STORE_DIR,
        "message": build_rebuild_message(indexed_files, len(manual_paths), failed_files),
    }


def load_existing_index() -> bool:
    return get_vector_store() is not None


def get_all_manual_paths() -> list[Path]:
    manual_paths: list[Path] = []
    seen: set[Path] = set()
    for _source_dir, directory in MANUAL_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_MANUAL_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            manual_paths.append(path)
    return manual_paths


def sort_manual_paths_for_image_knowledge(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=manual_image_priority)


def manual_image_priority(path: Path) -> tuple[int, str]:
    metadata = extract_document_metadata(path)
    manual_type = str(metadata.get("manual_type", ""))
    doc_type = str(metadata.get("doc_type", "")).lower()
    filename = path.name.lower()
    if "s120" in doc_type or "s120" in filename:
        return (0, path.name)
    if manual_type == "diagnosis":
        return (1, path.name)
    if "alarm" in doc_type or "报警" in path.name:
        return (2, path.name)
    return (9, path.name)


def get_manual_source_dir(file_path: str | Path) -> str:
    path = Path(file_path).resolve()
    for source_dir, directory in MANUAL_DIRS:
        try:
            path.relative_to(directory.resolve())
            return source_dir
        except ValueError:
            continue
    return "unknown"


def find_manual_path(filename: str, source_dir: str = "") -> Path | None:
    filename_path = Path(filename)
    if filename_path.is_absolute() and filename_path.exists() and filename_path.is_file():
        return filename_path

    relative_match = find_manual_path_by_relative_path(filename)
    if relative_match is not None:
        return relative_match

    for current_source_dir, directory in MANUAL_DIRS:
        if source_dir and current_source_dir != source_dir:
            continue
        for candidate in directory.rglob(Path(filename).name):
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def find_manual_path_by_relative_path(relative_path: str) -> Path | None:
    if not relative_path:
        return None
    path = Path(relative_path)
    if path.is_absolute() and path.exists() and path.is_file():
        return path
    project_candidate = Path.cwd() / path
    if project_candidate.exists() and project_candidate.is_file():
        return project_candidate
    for _source_dir, directory in MANUAL_DIRS:
        candidate = directory / path
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def clear_vector_store() -> None:
    reset_vector_store_cache()
    if VECTOR_STORE_PATH.exists():
        shutil.rmtree(VECTOR_STORE_PATH)
    VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)


def build_metadata(path: Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_dir": get_manual_source_dir(path),
        "relative_path": get_manual_relative_path(path),
        **dict(metadata or {}),
    }


def get_manual_relative_path(file_path: str | Path) -> str:
    path = Path(file_path).resolve()
    try:
        return str(path.relative_to(Path.cwd().resolve()))
    except ValueError:
        pass
    for _source_dir, directory in MANUAL_DIRS:
        try:
            return str(path.relative_to(directory.parent.parent.resolve()))
        except ValueError:
            continue
    return str(path)


def delete_document_from_vector_store(relative_path: str) -> bool:
    if not relative_path:
        return False
    vector_store = get_vector_store()
    if vector_store is None:
        return False
    try:
        vector_store.delete(where={"relative_path": relative_path})
        if hasattr(vector_store, "persist"):
            vector_store.persist()
        return True
    except Exception as exc:
        print(f"[LangChain RAG] delete old document chunks skipped. reason: {exc}")
        return False


def build_rebuild_message(indexed_files: int, total_files: int, failed_files: list[dict[str, str]]) -> str:
    if total_files == 0:
        return "未发现可索引手册"
    if failed_files:
        return f"已索引 {indexed_files}/{total_files} 个文件，部分文件进入兼容检索模式"
    return f"已成功重建 {indexed_files} 个手册索引"


def count_fallback_chunks(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        try:
            return len(extract_pdf_chunks(path))
        except Exception:
            return 0
    try:
        return 1 if path.read_text(encoding="utf-8").strip() else 0
    except Exception:
        return 0
