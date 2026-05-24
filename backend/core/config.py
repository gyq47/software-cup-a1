import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = "设备检修知识检索与作业系统 API"
VERSION = "0.1.0"
API_PREFIX = "/api"
UPLOAD_DIR = "uploads"

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
QWEN_VL_MODEL = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus")
