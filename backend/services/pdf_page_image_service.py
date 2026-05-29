import re
from pathlib import Path
from typing import Any

from backend.core.config import MANUAL_PAGE_IMAGE_PATH
from backend.rag.metadata_service import extract_document_metadata

PAGE_IMAGE_DPI_SCALE = 1.4
PAGE_IMAGE_SUFFIX = ".png"


def ensure_pdf_page_images(
    file_path: str | Path,
    metadata: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict[int, str]:
    path = Path(file_path)
    if path.suffix.lower() != ".pdf" or not path.exists():
        return {}

    try:
        import fitz
    except Exception as exc:
        print(f"[Manual Page Image] PyMuPDF unavailable, skip page images. reason: {exc}")
        return {}

    document_metadata = extract_document_metadata(path, metadata)
    target_dir = build_page_image_dir(path, document_metadata)
    target_dir.mkdir(parents=True, exist_ok=True)

    page_images: dict[int, str] = {}
    try:
        with fitz.open(str(path)) as pdf:
            matrix = fitz.Matrix(PAGE_IMAGE_DPI_SCALE, PAGE_IMAGE_DPI_SCALE)
            for page_index in range(pdf.page_count):
                page_number = page_index + 1
                image_path = target_dir / f"page_{page_number}{PAGE_IMAGE_SUFFIX}"
                if not image_path.exists() or overwrite:
                    page = pdf.load_page(page_index)
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    pixmap.save(str(image_path))
                page_images[page_number] = to_relative_project_path(image_path)
    except Exception as exc:
        print(f"[Manual Page Image] render failed for {path.name}. reason: {exc}")
        return page_images

    return page_images


def build_page_image_dir(file_path: Path, metadata: dict[str, Any]) -> Path:
    device_dir = normalize_device_dir(str(metadata.get("device_model", "common")))
    manual_type = sanitize_path_segment(str(metadata.get("manual_type", "other")) or "other")
    pdf_stem = sanitize_path_segment(file_path.stem)
    return MANUAL_PAGE_IMAGE_PATH / device_dir / manual_type / pdf_stem


def normalize_device_dir(device_model: str) -> str:
    upper = device_model.upper()
    if "808D" in upper:
        return "808D"
    if "828D" in upper:
        return "828D"
    if "COMMON" in upper:
        return "common"
    return sanitize_path_segment(device_model or "common")


def sanitize_path_segment(value: str) -> str:
    safe_value = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value).strip("._")
    return safe_value or "unknown"


def to_relative_project_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_page_image_path(relative_path: str) -> Path | None:
    if not relative_path:
        return None

    raw_path = Path(relative_path)
    candidate = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
    resolved = candidate.resolve()
    base = MANUAL_PAGE_IMAGE_PATH.resolve()

    try:
        resolved.relative_to(base)
    except ValueError:
        return None

    if resolved.suffix.lower() != PAGE_IMAGE_SUFFIX or not resolved.exists() or not resolved.is_file():
        return None
    return resolved
