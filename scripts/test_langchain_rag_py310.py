#!/usr/bin/env python3
"""Smoke-test the Python 3.10 + LangChain RAG route."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_INPUT = PROJECT_ROOT / "backend/data/processed/manual_text_chunks_test_v2.jsonl"


def main() -> int:
    args = parse_args()
    report: dict[str, object] = {
        "python_version": sys.version.split()[0],
        "python_ge_310": sys.version_info >= (3, 10),
        "imports": {},
        "input": str(Path(args.input).resolve()),
        "dry_run": args.dry_run,
    }
    if sys.version_info < (3, 10):
        report["error"] = "Python 3.10+ is required for the py310 LangChain route."
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    for module_name in ("langchain", "langchain_core", "langchain_text_splitters", "chromadb"):
        report["imports"][module_name] = import_available(module_name)

    input_path = Path(args.input)
    report["input_exists"] = input_path.exists()
    report["input_line_count"] = count_lines(input_path) if input_path.exists() else 0

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if all(report["imports"].values()) and report["input_exists"] else 2

    install_test_dependency_stubs()

    from backend.rag.langchain_pipeline import run_langchain_chat

    device_gate_tests = run_device_gate_unit_tests()
    report["device_gate_tests"] = device_gate_tests

    tests = [
        ("808D alarm", "808D 报警 20000 怎么处理？", "SINUMERIK 808D"),
        ("828D alarm", "828D 驱动报警如何诊断？", "SINUMERIK 828D"),
        ("808D interface", "808D X21 接口有什么作用？", "SINUMERIK 808D"),
        ("828D parameter", "828D 参数手册里 MD34030 相关内容是什么？", "SINUMERIK 828D"),
    ]
    results = []
    for name, question, device_model in tests:
        result = run_langchain_chat(question, top_k=args.top_k, device_model=device_model)
        contexts = result.get("contexts") or []
        devices = sorted({str(context.get("device_model", "")) for context in contexts})
        retrieval_filter = result.get("retrieval_filter", {})
        mixed_devices = [
            device
            for device in devices
            if is_explicit_other_device(device, device_model)
        ]
        results.append(
            {
                "name": name,
                "question": question,
                "requested_device_model": device_model,
                "context_count": len(contexts),
                "devices": devices,
                "retrieval_backend": retrieval_filter.get("retrieval_backend", ""),
                "filter_fallback": bool(retrieval_filter.get("filter_fallback", False)),
                "device_gate_dropped_count": int(retrieval_filter.get("device_gate_dropped_count") or 0),
                "device_gate_dropped_devices": retrieval_filter.get("device_gate_dropped_devices", []),
                "degraded": bool(result.get("degraded", False)),
                "mixed_device": bool(mixed_devices),
                "mixed_devices": mixed_devices,
                "top_sources": [
                    {
                        "device_model": context.get("device_model", ""),
                        "pdf_filename": context.get("pdf_filename", ""),
                        "page_number": context.get("page_number", ""),
                        "source_type": context.get("source_type", ""),
                        "chunk_id": context.get("chunk_id", ""),
                    }
                    for context in contexts[:3]
                ],
            }
        )
    report["tests"] = results
    report["success"] = all(item["passed"] for item in device_gate_tests) and all(
        not item["mixed_device"] and (item["context_count"] > 0 or item["filter_fallback"])
        for item in results
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Python 3.10 + LangChain RAG route.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def import_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def install_test_dependency_stubs() -> None:
    if import_available("dotenv") is False:
        dotenv_stub = types.ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda *args, **kwargs: False
        sys.modules["dotenv"] = dotenv_stub

    if import_available("openai") is False:
        openai_stub = types.ModuleType("openai")

        class OpenAIError(Exception):
            pass

        class OpenAI:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=self._create),
                )

            def _create(self, *args: object, **kwargs: object) -> object:
                raise OpenAIError("openai package is not installed in this test environment")

        openai_stub.OpenAI = OpenAI
        openai_stub.OpenAIError = OpenAIError
        sys.modules["openai"] = openai_stub

    if import_available("pypdf") is False:
        pypdf_stub = types.ModuleType("pypdf")

        class PdfReader:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.pages: list[object] = []

        pypdf_stub.PdfReader = PdfReader
        sys.modules["pypdf"] = pypdf_stub


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def run_device_gate_unit_tests() -> list[dict[str, object]]:
    from backend.rag import langchain_pipeline

    gate_cases = [
        (
            "808D drops explicit 828D",
            "SINUMERIK 808D",
            [
                {"chunk_id": "a", "device_model": "SINUMERIK 808D"},
                {"chunk_id": "b", "device_model": "SINUMERIK 828D"},
                {"chunk_id": "c", "device_model": "common"},
                {"chunk_id": "d", "device_model": ""},
            ],
            ["a", "c", "d"],
            ["SINUMERIK 828D"],
        ),
        (
            "828D drops explicit 808D",
            "SINUMERIK 828D",
            [
                {"chunk_id": "a", "device_model": "SINUMERIK 808D"},
                {"chunk_id": "b", "device_model": "SINUMERIK 828D"},
                {"chunk_id": "c", "device_model": "general"},
            ],
            ["b", "c"],
            ["SINUMERIK 808D"],
        ),
    ]
    results: list[dict[str, object]] = []
    for name, requested_device, contexts, expected_ids, expected_dropped_devices in gate_cases:
        kept, gate_info = langchain_pipeline.apply_device_gate(contexts, requested_device)
        kept_ids = [str(context.get("chunk_id")) for context in kept]
        dropped_devices = gate_info.get("device_gate_dropped_devices", [])
        passed = kept_ids == expected_ids and dropped_devices == expected_dropped_devices
        results.append(
            {
                "name": name,
                "passed": passed,
                "kept_ids": kept_ids,
                "expected_ids": expected_ids,
                "dropped_devices": dropped_devices,
                "expected_dropped_devices": expected_dropped_devices,
            }
        )

    results.append(run_fallback_preservation_unit_test(langchain_pipeline))
    return results


def run_fallback_preservation_unit_test(langchain_pipeline: object) -> dict[str, object]:
    original_generate = langchain_pipeline.generate_rag_contexts_with_info
    original_exact = langchain_pipeline.exact_match_contexts

    def fake_generate(_question: str, top_k: int, filters: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object]]:
        return [
            {
                "chunk_id": "wrong-device",
                "content": "828D only",
                "device_model": "SINUMERIK 828D",
                "final_score": 1.0,
                "filter_fallback": True,
                "retrieval_backend": "chroma",
            }
        ], {
            "used_device_filter": True,
            "requested_device_model": "SINUMERIK 808D",
            "filter_fallback": True,
            "filter_message": "当前设备型号下依据不足，已扩展到全库检索",
            "retrieval_backend": "chroma",
        }

    def fake_exact(_question: str, _query_info: dict[str, object], limit: int = 10) -> list[dict[str, object]]:
        return []

    try:
        langchain_pipeline.generate_rag_contexts_with_info = fake_generate
        langchain_pipeline.exact_match_contexts = fake_exact
        contexts, retrieval_filter = langchain_pipeline.hybrid_retrieve_contexts(
            "808D 测试问题",
            top_k=5,
            query_info={"device_model": "SINUMERIK 808D", "identifiers": [], "keywords": []},
        )
    finally:
        langchain_pipeline.generate_rag_contexts_with_info = original_generate
        langchain_pipeline.exact_match_contexts = original_exact

    passed = (
        contexts == []
        and bool(retrieval_filter.get("filter_fallback", False))
        and int(retrieval_filter.get("device_gate_dropped_count") or 0) == 1
        and retrieval_filter.get("device_gate_dropped_devices") == ["SINUMERIK 828D"]
    )
    return {
        "name": "fallback state survives device gate",
        "passed": passed,
        "context_count": len(contexts),
        "filter_fallback": bool(retrieval_filter.get("filter_fallback", False)),
        "device_gate_dropped_count": int(retrieval_filter.get("device_gate_dropped_count") or 0),
        "device_gate_dropped_devices": retrieval_filter.get("device_gate_dropped_devices", []),
    }


def is_explicit_other_device(device: str, requested_device: str) -> bool:
    normalized = str(device or "").strip().upper()
    requested = str(requested_device or "").strip().upper()
    if not normalized or normalized in {"COMMON", "GENERAL", "通用", "通用知识", "通用设备"}:
        return False
    if "808D" in requested:
        return "828D" in normalized
    if "828D" in requested:
        return "808D" in normalized
    return False


if __name__ == "__main__":
    raise SystemExit(main())
