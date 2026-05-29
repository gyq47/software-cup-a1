import re
from pathlib import Path
from typing import Any


KNOWN_BRANDS = ("西门子", "SINUMERIK", "Siemens", "无极", "隆鑫", "本田", "雅马哈", "铃木", "川崎", "豪爵")
MODEL_PATTERN = re.compile(r"(SINUMERIK\s*\d{2,4}[A-Za-z]*|\d{2,4}[A-Za-z]*)", re.IGNORECASE)
PATH_MODEL_MAP = {
    "808D": "SINUMERIK 808D",
    "828D": "SINUMERIK 828D",
    "COMMON": "common",
}
PATH_MANUAL_TYPES = {
    "diagnosis",
    "parameter",
    "plc",
    "electrical",
    "drive",
    "operation",
    "repair",
    "other",
}


def extract_document_metadata(file_path: str | Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    path = Path(file_path)
    filename = path.name
    stem = path.stem
    base_metadata = dict(metadata or {})

    path_device_model = extract_device_model_from_path(path)
    path_manual_type = extract_manual_type_from_path(path)
    brand = base_metadata.get("brand") or extract_brand(stem)
    device_model = base_metadata.get("device_model") or path_device_model or extract_device_model(stem)
    manual_type = base_metadata.get("manual_type") or path_manual_type or extract_manual_type(stem)

    doc_type = base_metadata.get("doc_type") or extract_doc_type_detail(stem, manual_type)
    return {
        "filename": filename,
        "source": str(path),
        "brand": brand,
        "device_model": device_model,
        "displacement": base_metadata.get("displacement", extract_displacement(device_model or stem)),
        "manual_type": manual_type,
        "doc_type": doc_type,
        "language": base_metadata.get("language", "zh"),
        "relative_path": base_metadata.get("relative_path", build_relative_path(path)),
        "source_dir": base_metadata.get("source_dir", ""),
        **base_metadata,
    }


def extract_device_model_from_path(path: str | Path) -> str:
    parts = [part.upper() for part in Path(path).parts]
    for part in parts:
        if part in PATH_MODEL_MAP:
            return PATH_MODEL_MAP[part]
    return ""


def build_relative_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def extract_manual_type_from_path(path: str | Path) -> str:
    parts = [part.lower() for part in Path(path).parts]
    for part in parts:
        if part in PATH_MANUAL_TYPES:
            return part
    return ""


def extract_brand(text: str) -> str:
    normalized = text.upper()
    if "SINUMERIK" in normalized or "SIEMENS" in normalized or "西门子" in text:
        return "西门子"
    for brand in KNOWN_BRANDS:
        if brand in text:
            return brand
    return ""


def extract_device_model(text: str) -> str:
    upper_text = str(text or "").upper()
    if "808D" in upper_text:
        return "SINUMERIK 808D"
    if "828D" in upper_text:
        return "SINUMERIK 828D"
    if upper_text.strip() == "COMMON":
        return "common"
    return ""


def normalize_device_model(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper_text = text.upper()
    if "808D" in upper_text:
        return "SINUMERIK 808D"
    if "828D" in upper_text:
        return "SINUMERIK 828D"
    if upper_text == "COMMON":
        return "common"
    extracted = extract_device_model(text)
    return extracted or text


def extract_displacement(text: str) -> str:
    match = re.search(r"(\d{2,4})", text or "")
    return match.group(1) if match else ""


def extract_manual_type(text: str) -> str:
    upper_text = text.upper()
    if "诊断" in text:
        return "diagnosis"
    if "参数" in text:
        return "parameter"
    if "PLC" in upper_text or "子程序库" in text:
        return "plc"
    if "电气安装" in text or "电气" in text:
        return "electrical"
    if "驱动" in text:
        return "drive"
    if "操作说明" in text or "简明操作" in text or "操作" in text:
        return "operation"
    if "维修" in text:
        return "repair"
    if "用户" in text or "使用" in text:
        return "operation"
    if "零件" in text:
        return "parts"
    return "other"


def extract_doc_type_detail(text: str, manual_type: str) -> str:
    upper_text = text.upper()
    details: list[str] = [manual_type or "other"]
    if "S120" in upper_text or "SINAMICS" in upper_text:
        details.append("s120")
    if "报警" in text:
        details.append("alarm")
    if "诊断" in text and "diagnosis" not in details:
        details.append("diagnosis")
    if "开机调试" in text or "调试" in text:
        details.append("commissioning")
    return "_".join(dict.fromkeys(item for item in details if item))


def extract_filters_from_query(query: str) -> dict[str, str]:
    device_model = extract_device_model(query)
    filters: dict[str, str] = {}
    if device_model:
        filters["device_model"] = device_model
    return filters
