#!/usr/bin/env python3
"""Test Qwen-VL connectivity with one existing manual page image.

This script does not write to Chroma, does not index documents, and does not
run RAG. It only verifies whether the configured vision model endpoint can be
reached from the current environment.
"""

import argparse
import base64
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_IMAGE = (
    PROJECT_ROOT
    / "backend/data/manual_pages/808D/electrical/西门子SINUMERIK808D_电气安装手册_操作说明/page_26.png"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Qwen-VL connection.")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(PROJECT_ROOT / ".env")

    from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_VL_MODEL

    started_at = time.perf_counter()
    result = {
        "success": False,
        "model_name": QWEN_VL_MODEL,
        "duration": 0.0,
        "response_preview": "",
        "error_type": "",
        "error_message": "",
    }

    try:
        if not QWEN_API_KEY:
            raise RuntimeError("QWEN_API_KEY 未配置")
        if not TEST_IMAGE.exists():
            raise FileNotFoundError(f"测试图片不存在：{TEST_IMAGE}")

        client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, timeout=args.timeout)
        response = client.chat.completions.create(
            model=QWEN_VL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是工业设备维修手册图片识别测试助手。请用一句话描述图片内容。",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请简要说明这张维修手册页面截图里有什么。"},
                        {
                            "type": "image_url",
                            "image_url": {"url": build_data_url(TEST_IMAGE)},
                        },
                    ],
                },
            ],
            max_tokens=120,
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        result.update(
            {
                "success": True,
                "response_preview": content[:500],
            }
        )
    except Exception as exc:
        result.update(
            {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
    finally:
        result["duration"] = round(time.perf_counter() - started_at, 2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_data_url(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


if __name__ == "__main__":
    main()
