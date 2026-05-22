import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from backend.core.config import UPLOAD_DIR

router = APIRouter(prefix="/manual", tags=["manual"])

MANUAL_UPLOAD_DIR = Path(UPLOAD_DIR) / "manuals"


def sanitize_filename(filename: str) -> str:
    original_name = Path(filename).name
    safe_name = re.sub(r"[^\w.-]+", "_", original_name).strip("._")
    return safe_name or "manual.pdf"


def build_unique_filename(filename: str) -> str:
    safe_name = sanitize_filename(filename)
    file_path = Path(safe_name)
    stem = file_path.stem or "manual"
    suffix = file_path.suffix.lower() or ".pdf"

    candidate = f"{stem}{suffix}"
    index = 1
    while (MANUAL_UPLOAD_DIR / candidate).exists():
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return candidate


@router.post("/upload")
def upload_manual(file: UploadFile = File(...)) -> dict[str, bool | str]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".pdf":
        return {
            "success": False,
            "error": "只允许上传 PDF 文件",
        }

    MANUAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_filename = build_unique_filename(filename)
    saved_path = MANUAL_UPLOAD_DIR / saved_filename

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "success": True,
        "filename": saved_filename,
    }
