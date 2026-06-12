#!/usr/bin/env python3
"""Verify ChromaDB PersistentClient add/query on Python 3.9."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path


def main() -> None:
    started_at = time.perf_counter()
    temp_dir = Path(tempfile.mkdtemp(prefix="chromadb_py39_"))
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(temp_dir))
        collection = client.get_or_create_collection(name="py39_smoke_test")
        collection.add(
            ids=["doc-1", "doc-2"],
            documents=[
                "SINUMERIK 808D X21 FAST I/O 接口针脚分配测试",
                "SINUMERIK 828D S120 报警诊断页面测试",
            ],
            metadatas=[
                {"device_model": "SINUMERIK 808D", "source_type": "manual_text"},
                {"device_model": "SINUMERIK 828D", "source_type": "manual_text"},
            ],
        )
        result = collection.query(query_texts=["S120 报警诊断"], n_results=1)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        print(
            json.dumps(
                {
                    "success": True,
                    "chromadb_version": getattr(chromadb, "__version__", ""),
                    "persist_dir": str(temp_dir),
                    "count": collection.count(),
                    "query_ids": result.get("ids", []),
                    "duration_ms": duration_ms,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
