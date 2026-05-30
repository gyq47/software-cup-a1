import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = "设备检修知识检索与作业系统 API"
VERSION = "0.1.0"
API_PREFIX = "/api"
UPLOAD_DIR = "uploads"
MANUAL_UPLOAD_DIR = os.getenv("MANUAL_UPLOAD_DIR", "uploads/manuals")
MANUAL_STATIC_DIR = os.getenv("MANUAL_STATIC_DIR", "backend/data/manuals")
MANUAL_PAGE_IMAGE_DIR = os.getenv("MANUAL_PAGE_IMAGE_DIR", "backend/data/manual_pages")
IMAGE_KNOWLEDGE_DIR = os.getenv("IMAGE_KNOWLEDGE_DIR", "backend/data/processed/image_knowledge")
KNOWLEDGE_GRAPH_DIR = os.getenv("KNOWLEDGE_GRAPH_DIR", "backend/data/knowledge_graph")

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
QWEN_VL_MODEL = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus")

RAG_BACKEND = os.getenv("RAG_BACKEND", "langchain")
VECTOR_STORE_DIR = os.getenv("VECTOR_STORE_DIR", "backend/data/vector_store/chroma")
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))
IMAGE_KNOWLEDGE_MAX_PAGES = int(os.getenv("IMAGE_KNOWLEDGE_MAX_PAGES", "100"))
IMAGE_KNOWLEDGE_QWEN_TIMEOUT = int(os.getenv("IMAGE_KNOWLEDGE_QWEN_TIMEOUT", "12"))
IMAGE_KNOWLEDGE_VL_MODE = os.getenv("IMAGE_KNOWLEDGE_VL_MODE", "fast").lower()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DISABLE_CHROMA = env_bool("DISABLE_CHROMA", False)
DISABLE_PDF_PREVIEW = env_bool("DISABLE_PDF_PREVIEW", False)
DISABLE_IMAGE_KNOWLEDGE = env_bool("DISABLE_IMAGE_KNOWLEDGE", False)
DISABLE_LOCAL_EMBEDDING = env_bool("DISABLE_LOCAL_EMBEDDING", False)


def resolve_project_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


MANUAL_UPLOAD_PATH = resolve_project_path(MANUAL_UPLOAD_DIR)
MANUAL_STATIC_PATH = resolve_project_path(MANUAL_STATIC_DIR)
MANUAL_PAGE_IMAGE_PATH = resolve_project_path(MANUAL_PAGE_IMAGE_DIR)
IMAGE_KNOWLEDGE_PATH = resolve_project_path(IMAGE_KNOWLEDGE_DIR)
KNOWLEDGE_GRAPH_PATH = resolve_project_path(KNOWLEDGE_GRAPH_DIR) / "graph.json"
VECTOR_STORE_PATH = resolve_project_path(VECTOR_STORE_DIR)

SUPPORTED_DEVICE_MODELS = ("808D", "828D", "common")
SUPPORTED_MANUAL_TYPES = (
    "diagnosis",
    "parameter",
    "plc",
    "electrical",
    "drive",
    "operation",
    "repair",
    "other",
)
