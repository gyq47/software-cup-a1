#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    install_test_dependency_stubs()

    from backend.tools.rag_tool import apply_device_gate_tool

    cases = [
        {
            "name": "808D keeps 808D common empty and drops 828D",
            "device_model": "SINUMERIK 808D",
            "contexts": [
                context("808d", "SINUMERIK 808D"),
                context("828d", "SINUMERIK 828D"),
                context("common", "common"),
                context("general", "general"),
                context("empty", ""),
            ],
            "expected_kept": ["808d", "common", "general", "empty"],
            "expected_dropped_devices": ["SINUMERIK 828D"],
        },
        {
            "name": "828D keeps 828D common and drops 808D",
            "device_model": "SINUMERIK 828D",
            "contexts": [
                context("808d", "SINUMERIK 808D"),
                context("828d", "SINUMERIK 828D"),
                context("common", "通用"),
            ],
            "expected_kept": ["828d", "common"],
            "expected_dropped_devices": ["SINUMERIK 808D"],
        },
    ]
    results = []
    for case in cases:
        result = apply_device_gate_tool(
            case["contexts"],
            case["device_model"],
            {
                "filter_fallback": True,
                "filter_message": "当前设备型号下依据不足，已扩展检索范围",
                "retrieval_backend": "mock",
            },
        )
        filtered = result.get("data", {}).get("filtered_contexts", [])
        retrieval_filter = result.get("data", {}).get("retrieval_filter", {})
        kept_ids = [item.get("chunk_id") for item in filtered]
        mixed_devices = [
            item.get("device_model")
            for item in filtered
            if is_cross_device(str(item.get("device_model") or ""), str(case["device_model"]))
        ]
        passed = (
            result.get("status") == "success"
            and kept_ids == case["expected_kept"]
            and retrieval_filter.get("device_gate_dropped_devices") == case["expected_dropped_devices"]
            and bool(retrieval_filter.get("filter_fallback", False))
            and not mixed_devices
        )
        results.append(
            {
                "name": case["name"],
                "passed": passed,
                "kept_ids": kept_ids,
                "mixed_devices": mixed_devices,
                "filter_fallback": bool(retrieval_filter.get("filter_fallback", False)),
                "device_gate_dropped_devices": retrieval_filter.get("device_gate_dropped_devices", []),
            }
        )

    report = {"success": all(item["passed"] for item in results), "tests": results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


def context(chunk_id: str, device_model: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "device_model": device_model,
        "content": f"{chunk_id} content",
        "retrieval_backend": "mock",
    }


def is_cross_device(device_model: str, requested_device: str) -> bool:
    upper_device = device_model.upper()
    upper_requested = requested_device.upper()
    if not upper_device or upper_device in {"COMMON", "GENERAL", "通用"}:
        return False
    if "808D" in upper_requested:
        return "828D" in upper_device
    if "828D" in upper_requested:
        return "808D" in upper_device
    return False


def install_test_dependency_stubs() -> None:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: False
    sys.modules.setdefault("dotenv", dotenv_stub)

    openai_stub = types.ModuleType("openai")

    class OpenAIError(Exception):
        pass

    class OpenAI:
        pass

    openai_stub.OpenAI = OpenAI
    openai_stub.OpenAIError = OpenAIError
    sys.modules.setdefault("openai", openai_stub)

    pypdf_stub = types.ModuleType("pypdf")

    class PdfReader:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.pages = []

    pypdf_stub.PdfReader = PdfReader
    sys.modules.setdefault("pypdf", pypdf_stub)


if __name__ == "__main__":
    raise SystemExit(main())

