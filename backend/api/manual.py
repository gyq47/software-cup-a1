import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.core.config import MANUAL_UPLOAD_PATH, VECTOR_STORE_PATH
from backend.rag.indexing_service import (
    MANUAL_DIRS,
    delete_document_from_vector_store,
    find_manual_path,
    find_manual_path_by_relative_path,
    get_all_manual_paths,
    get_manual_relative_path,
    get_manual_source_dir,
    index_document,
    rebuild_index,
)
from backend.rag.metadata_service import extract_document_metadata
from backend.services.pdf_service import extract_pdf_chunks
from backend.services.pdf_page_image_service import resolve_page_image_path

router = APIRouter(prefix="/manual", tags=["manual"])

MANUAL_UPLOAD_DIR = MANUAL_UPLOAD_PATH


class ManualReindexRequest(BaseModel):
    filename: str = ""
    source_dir: str = ""
    relative_path: str = ""


def sanitize_filename(filename: str) -> str:
    original_name = Path(filename).name
    safe_name = re.sub(r"[^\w.-]+", "_", original_name).strip("._")
    return safe_name or "manual.pdf"


def normalize_device_model_dir(device_model: str | None) -> str:
    value = (device_model or "common").strip()
    upper = value.upper()
    if "808D" in upper:
        return "808D"
    if "828D" in upper:
        return "828D"
    if upper == "COMMON":
        return "common"
    return "common"


def normalize_manual_type_dir(manual_type: str | None) -> str:
    value = (manual_type or "other").strip().lower()
    allowed = {"diagnosis", "parameter", "plc", "electrical", "drive", "operation", "repair", "other"}
    return value if value in allowed else "other"


def build_unique_filename(directory: Path, filename: str) -> str:
    safe_name = sanitize_filename(filename)
    file_path = Path(safe_name)
    stem = file_path.stem or "manual"
    suffix = file_path.suffix.lower() or ".pdf"

    candidate = f"{stem}{suffix}"
    index = 1
    while (directory / candidate).exists():
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return candidate


@router.post("/upload")
def upload_manual(
    file: UploadFile = File(...),
    device_model: str = Form(default="common"),
    manual_type: str = Form(default="other"),
) -> dict[str, bool | int | str]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".pdf":
        return {
            "success": False,
            "error": "只允许上传 PDF 文件",
        }

    device_dir = normalize_device_model_dir(device_model)
    manual_type_dir = normalize_manual_type_dir(manual_type)
    target_dir = MANUAL_UPLOAD_DIR / device_dir / manual_type_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_filename = build_unique_filename(target_dir, filename)
    saved_path = target_dir / saved_filename

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    index_result = index_document(saved_path)
    metadata = index_result.get("metadata", {})

    return {
        "success": True,
        "filename": saved_filename,
        "relative_path": str(metadata.get("relative_path", get_manual_relative_path(saved_path))),
        "device_model": str(metadata.get("device_model", device_dir)),
        "manual_type": str(metadata.get("manual_type", manual_type_dir)),
        "indexed": bool(index_result.get("indexed", False)),
        "chunk_count": int(index_result.get("chunks", 0)),
        "chunks": int(index_result.get("chunks", 0)),
        "message": str(index_result.get("message", "")),
        "index_message": str(index_result.get("message", "")),
    }


@router.get("/list")
def list_manuals(
    device_model: str | None = Query(default=None),
    manual_type: str | None = Query(default=None),
) -> dict[str, Any]:
    manuals = [
        item
        for item in (build_manual_item(path) for path in get_all_manual_paths())
        if matches_manual_filters(item, device_model, manual_type)
    ]
    return {
        "items": manuals,
        "total": len(manuals),
        "indexed_count": sum(1 for item in manuals if item["indexed"]),
        "total_chunks": sum(int(item["chunk_count"]) for item in manuals),
        "vector_store_dir": str(VECTOR_STORE_PATH),
        "vector_store_ready": is_vector_store_ready(),
    }


@router.post("/rebuild-index")
def rebuild_manual_index() -> dict[str, Any]:
    result = rebuild_index()
    return {
        "success": bool(result.get("success", False)),
        **result,
    }


@router.post("/reindex")
def reindex_manual(request: ManualReindexRequest) -> dict[str, Any]:
    manual_path = (
        find_manual_path_by_relative_path(request.relative_path)
        if request.relative_path
        else find_manual_path(request.filename, request.source_dir)
    )
    if manual_path is None:
        raise HTTPException(status_code=404, detail="未找到指定手册")

    relative_path = get_manual_relative_path(manual_path)
    delete_document_from_vector_store(relative_path)
    result = index_document(manual_path)
    metadata = result.get("metadata", {})
    return {
        "success": bool(result.get("indexed", False)),
        "filename": manual_path.name,
        "relative_path": str(metadata.get("relative_path", relative_path)),
        "source_dir": get_manual_source_dir(manual_path),
        "device_model": str(metadata.get("device_model", "")),
        "manual_type": str(metadata.get("manual_type", "")),
        "indexed": bool(result.get("indexed", False)),
        "chunk_count": int(result.get("chunks", 0)),
        "chunks": int(result.get("chunks", 0)),
        "message": str(result.get("message", "")),
    }


@router.get("/page-image")
def get_manual_page_image(path: str = Query(..., description="backend/data/manual_pages 下的页面截图相对路径")) -> FileResponse:
    image_path = resolve_page_image_path(path)
    if image_path is None:
        raise HTTPException(status_code=404, detail="未找到手册页面截图")
    return FileResponse(image_path, media_type="image/png")


def build_manual_item(path: Path) -> dict[str, Any]:
    stat = path.stat()
    source_dir = get_manual_source_dir(path)
    metadata = extract_document_metadata(path, {"source_dir": source_dir})
    chunk_count = count_manual_chunks(path)
    indexed = is_vector_store_ready()
    return {
        "filename": path.name,
        "relative_path": metadata.get("relative_path", get_manual_relative_path(path)),
        "device_model": metadata.get("device_model", ""),
        "manual_type": metadata.get("manual_type", ""),
        "doc_type": metadata.get("doc_type", metadata.get("manual_type", "")),
        "source_dir": source_dir,
        "file_size": stat.st_size,
        "updated_at": stat.st_mtime,
        "indexed": indexed,
        "index_status": "已建立" if indexed else "未建立",
        "chunk_count": chunk_count,
        "chunks": chunk_count,
    }


def matches_manual_filters(
    item: dict[str, Any],
    device_model: str | None,
    manual_type: str | None,
) -> bool:
    if device_model:
        requested = normalize_device_model_dir(device_model).upper()
        current = str(item.get("device_model", "")).upper()
        if requested == "COMMON":
            if current != "COMMON":
                return False
        elif requested not in current:
            return False
    if manual_type and manual_type != "全部":
        if item.get("manual_type") != manual_type:
            return False
    return True


def count_manual_chunks(path: Path) -> int:
    if path.suffix.lower() != ".pdf":
        return 0
    try:
        return len(extract_pdf_chunks(path))
    except Exception:
        return 0


def is_vector_store_ready() -> bool:
    return VECTOR_STORE_PATH.exists() and any(VECTOR_STORE_PATH.iterdir())
