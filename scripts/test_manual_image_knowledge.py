#!/usr/bin/env python3
"""One-off validation for PDF page-image knowledge ingestion.

This script intentionally does not change the normal indexing pipeline. It
extracts image knowledge for a few selected SINUMERIK 828D / S120 manual pages,
writes those manual_image Documents into the existing Chroma collection, and
then runs a few retrieval checks.
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PAGES = (405, 407, 420, 438, 452, 462, 463, 497, 523, 535)
PDF_PATH = PROJECT_ROOT / "backend/data/manuals/828D/diagnosis/SINUMERIK 828D SINAMICS S120 报警 诊断手册.pdf"
IMAGE_DIR = PROJECT_ROOT / "backend/data/manual_pages/828D/diagnosis/SINUMERIK_828D_SINAMICS_S120_报警_诊断手册"
QUERIES = ("S120报警界面", "驱动报警页面", "报警参数界面")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate manual_image knowledge ingestion.")
    parser.add_argument("--pages", default=",".join(str(page) for page in DEFAULT_PAGES), help="Comma separated page numbers.")
    parser.add_argument("--image-path", default="", help="Single page image path for direct validation.")
    parser.add_argument("--device-model", default="", help="Device model for the generated manual_image document.")
    parser.add_argument("--manual-type", default="", help="Manual type for the generated manual_image document.")
    parser.add_argument("--pdf-filename", default="", help="Original PDF filename for metadata.")
    parser.add_argument("--page-number", type=int, default=0, help="Original 1-based PDF page number.")
    parser.add_argument("--query", default="", help="Retrieval query for validation.")
    parser.add_argument("--timeout", type=int, default=60, help="Qwen-VL timeout seconds for this validation run.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--reset-existing", action="store_true", help="Delete previous test manual_image chunks for these pages before adding.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ["IMAGE_KNOWLEDGE_QWEN_TIMEOUT"] = str(args.timeout)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    from backend.rag.retriever import retrieve_documents_with_info
    from backend.rag.vector_store import add_documents_to_vector_store, get_vector_store
    from backend.core.config import VECTOR_STORE_PATH

    direct_mode = bool(args.image_path)
    pages = [int(item.strip()) for item in args.pages.split(",") if item.strip()]
    if len(pages) > 10:
        raise SystemExit("最多只允许验证 10 页")
    if not direct_mode and not PDF_PATH.exists():
        raise SystemExit(f"未找到 PDF：{PDF_PATH}")

    pdf_path, metadata, selected_page_images, query, device_filter = build_validation_context(args)
    if not selected_page_images:
        raise SystemExit("未找到可用页截图")

    before_count = count_manual_image_chunks(VECTOR_STORE_PATH)
    if args.reset_existing:
        delete_existing_test_chunks(get_vector_store(), pdf_path.name, selected_page_images)

    documents: list[Any] = []
    timing_records: list[dict[str, Any]] = []
    script_started_at = time.perf_counter()
    for page, image_path in selected_page_images.items():
        page_documents, timing = build_manual_image_document(pdf_path, metadata, page, Path(image_path), args.timeout)
        timing_records.append(timing)
        print(
            "[manual_image] "
            f"page={page} docs={len(page_documents)} "
            f"total_ms={timing['total_ms']} "
            f"ocr_ms={timing['ocr_ms']} "
            f"qwen_vl_ms={timing['qwen_vl_ms']}",
            flush=True,
        )
        documents.extend(page_documents)

    chroma_started_at = time.perf_counter()
    indexed = add_documents_to_vector_store(documents)
    chroma_write_ms = elapsed_ms(chroma_started_at)
    after_count = count_manual_image_chunks(VECTOR_STORE_PATH)
    retrieval_started_at = time.perf_counter()

    print("\nA. 实际进入 Chroma 的 manual_image 数量")
    print(f"before={before_count}, after={after_count}, added_this_run={len(documents)}, indexed={indexed}")

    print("\nA1. 耗时拆分")
    for timing in timing_records:
        print(timing)

    print("\nB. 示例 Document")
    if documents:
        print(documents[0].page_content[:1200])
    else:
        print("未生成有效 manual_image Document")

    print("\nC. 示例 metadata")
    if documents:
        print(documents[0].metadata)
    else:
        print("{}")

    print("\nD. 示例 RAG 召回结果")
    validation_queries = (query,) if query else QUERIES
    for query in validation_queries:
        results, filter_info = retrieve_documents_with_info(
            query,
            top_k=args.top_k,
            filters={"device_model": device_filter} if device_filter else None,
        )
        print(f"\nquery={query}")
        print(f"filter_info={filter_info}")
        for index, (document, score) in enumerate(results, start=1):
            doc_metadata = getattr(document, "metadata", {}) or {}
            print(
                f"{index}. source_type={doc_metadata.get('source_type', 'manual_text')} "
                f"page={doc_metadata.get('page')} score={score:.4f} "
                f"chunk_id={doc_metadata.get('chunk_id')}"
            )
            print(f"   {getattr(document, 'page_content', '')[:220].replace(chr(10), ' ')}")

        manual_image_results = search_manual_image_only(get_vector_store(), query, args.top_k, device_filter)
        print("manual_image_filtered_results=")
        for index, (document, score) in enumerate(manual_image_results, start=1):
            doc_metadata = getattr(document, "metadata", {}) or {}
            print(
                f"{index}. source_type={doc_metadata.get('source_type')} "
                f"page={doc_metadata.get('page')} score={score:.4f} "
                f"chunk_id={doc_metadata.get('chunk_id')}"
            )
            print(f"   {getattr(document, 'page_content', '')[:220].replace(chr(10), ' ')}")

    retrieval_verify_ms = elapsed_ms(retrieval_started_at)
    total_ms = elapsed_ms(script_started_at)

    print("\nE. Qwen-VL 平均耗时")
    qwen_values = [record["qwen_vl_ms"] for record in timing_records]
    average_qwen_ms = sum(qwen_values) / len(qwen_values) if qwen_values else 0
    print(f"{average_qwen_ms / 1000:.2f}s/page")
    print(f"chroma_write_ms={chroma_write_ms}")
    print(f"retrieval_verify_ms={retrieval_verify_ms}")
    print(f"total_ms={total_ms}")

    print("\nF. 如果超时，应如何调整 timeout")
    print("可运行：IMAGE_KNOWLEDGE_QWEN_TIMEOUT=90 venv/bin/python scripts/test_manual_image_knowledge.py --timeout 90")

    print("\nG. 是否建议保留该功能进入比赛版本")
    print("建议保留，但以小批量、缓存、手动触发方式进入比赛版本，不建议在演示时全量处理 3872 页。")


def build_validation_context(args: argparse.Namespace) -> tuple[Path, dict[str, Any], dict[int, str], str, str]:
    from backend.rag.indexing_service import build_metadata
    from backend.rag.metadata_service import extract_document_metadata, normalize_device_model

    if args.image_path:
        image_path = resolve_path(args.image_path)
        if not image_path.exists():
            raise SystemExit(f"测试图片不存在：{image_path}")
        if not args.pdf_filename or not args.page_number:
            raise SystemExit("--image-path 模式必须提供 --pdf-filename 和 --page-number")
        pdf_path = PROJECT_ROOT / args.pdf_filename
        metadata = extract_document_metadata(
            pdf_path,
            {
                "filename": args.pdf_filename,
                "source": args.pdf_filename,
                "relative_path": args.pdf_filename,
                "source_dir": "manual_page_image_test",
                "device_model": normalize_device_model(args.device_model),
                "manual_type": args.manual_type,
                "doc_type": args.manual_type,
            },
        )
        return (
            pdf_path,
            metadata,
            {args.page_number: str(image_path)},
            args.query or "X21 FAST I/O 接口针脚分配",
            normalize_device_model(args.device_model),
        )

    metadata = extract_document_metadata(PDF_PATH, build_metadata(PDF_PATH))
    selected_page_images = {
        page: str(IMAGE_DIR / f"page_{page}.png")
        for page in [int(item.strip()) for item in args.pages.split(",") if item.strip()]
        if (IMAGE_DIR / f"page_{page}.png").exists()
    }
    return PDF_PATH, metadata, selected_page_images, args.query, "SINUMERIK 828D"


def resolve_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def delete_existing_test_chunks(vector_store: Any, pdf_filename: str, page_images: dict[int, str]) -> None:
    if vector_store is None:
        return
    for page in page_images:
        try:
            vector_store.delete(where={"chunk_id": f"{pdf_filename}-image-p{page}"})
        except Exception as exc:
            print(f"[manual_image] cleanup skipped for page={page}. reason={exc}")


def count_manual_image_chunks(vector_store_path: Path) -> int:
    sqlite_path = vector_store_path / "chroma.sqlite3"
    if not sqlite_path.exists():
        return 0
    with sqlite3.connect(sqlite_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM embedding_metadata WHERE key='source_type' AND string_value='manual_image'"
        ).fetchone()
    return int(row[0]) if row else 0


def search_manual_image_only(vector_store: Any, query: str, top_k: int, device_model: str) -> list[tuple[Any, float]]:
    if vector_store is None:
        return []
    filters: dict[str, Any]
    if device_model:
        filters = {"$and": [{"device_model": device_model}, {"source_type": "manual_image"}]}
    else:
        filters = {"source_type": "manual_image"}
    try:
        return vector_store.similarity_search_with_score(query, k=top_k, filter=filters)
    except Exception as exc:
        print(f"[manual_image] filtered retrieval failed: {exc}", flush=True)
        return []


def build_manual_image_document(
    pdf_path: Path,
    metadata: dict[str, Any],
    page: int,
    image_path: Path,
    timeout: int,
) -> tuple[list[Any], dict[str, Any]]:
    from langchain_core.documents import Document
    from backend.services.pdf_image_knowledge_service import (
        build_document_content,
        has_useful_knowledge,
        merge_keywords,
        run_optional_ocr,
    )

    total_started_at = time.perf_counter()
    image_started_at = time.perf_counter()
    image_size_bytes = image_path.stat().st_size if image_path.exists() else 0
    image_width_height = read_image_size(image_path)
    image_load_ms = elapsed_ms(image_started_at)

    ocr_started_at = time.perf_counter()
    ocr_text = run_optional_ocr(image_path)
    ocr_ms = elapsed_ms(ocr_started_at)

    qwen_started_at = time.perf_counter()
    vision_result = call_qwen_vl_with_requests(image_path, timeout)
    qwen_vl_ms = elapsed_ms(qwen_started_at)

    document_started_at = time.perf_counter()
    image_summary = str(vision_result.get("summary") or "")
    keywords = merge_keywords(vision_result.get("keywords"), ocr_text, image_summary, vision_result.get("objects"))
    knowledge = {
        "ocr_text": ocr_text,
        "image_summary": image_summary,
        "keywords": keywords,
    }
    timing = {
        "page": page,
        "image_load_ms": image_load_ms,
        "image_size_bytes": image_size_bytes,
        "image_width_height": image_width_height,
        "ocr_ms": ocr_ms,
        "qwen_vl_ms": qwen_vl_ms,
        "document_build_ms": 0,
        "total_ms": 0,
    }
    if not has_useful_knowledge(knowledge):
        timing["document_build_ms"] = elapsed_ms(document_started_at)
        timing["total_ms"] = elapsed_ms(total_started_at)
        return [], timing

    page_content = build_document_content(
        pdf_filename=pdf_path.name,
        page_number=page,
        ocr_text=ocr_text,
        image_summary=image_summary,
        keywords=keywords,
    )
    doc_metadata = {
        **metadata,
        "source_type": "manual_image",
        "doc_type": "image_knowledge",
        "filename": pdf_path.name,
        "pdf_filename": pdf_path.name,
        "page": page,
        "page_number": page,
        "page_image_path": str(image_path.relative_to(PROJECT_ROOT)),
        "chunk_id": f"{pdf_path.name}-image-p{page}",
        "image_keywords": ", ".join(keywords),
    }
    timing["document_build_ms"] = elapsed_ms(document_started_at)
    timing["total_ms"] = elapsed_ms(total_started_at)
    return [Document(page_content=page_content, metadata=doc_metadata)], timing


def call_qwen_vl_with_requests(image_path: Path, timeout: int) -> dict[str, Any]:
    os.environ["IMAGE_KNOWLEDGE_QWEN_TIMEOUT"] = str(timeout)
    from backend.services.pdf_image_knowledge_service import analyze_manual_page_image

    return analyze_manual_page_image(image_path)


def read_image_size(image_path: Path) -> str:
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            return f"{image.width}x{image.height}"
    except Exception:
        return ""


def elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


if __name__ == "__main__":
    main()
