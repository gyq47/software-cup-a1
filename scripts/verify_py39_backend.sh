#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "[verify] python executable: $(${PYTHON_BIN} -c 'import sys; print(sys.executable)')"
PY_VERSION="$(${PYTHON_BIN} -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "[verify] python version: ${PY_VERSION}"

case "${PY_VERSION}" in
  3.9.*) ;;
  *)
    echo "[verify] ERROR: expected Python 3.9.x, got ${PY_VERSION}" >&2
    exit 1
    ;;
esac

${PYTHON_BIN} -m pip check

${PYTHON_BIN} - <<'PY'
import fastapi
import uvicorn
import chromadb
import numpy

print("[verify] fastapi", getattr(fastapi, "__version__", ""))
print("[verify] uvicorn", getattr(uvicorn, "__version__", ""))
print("[verify] chromadb", getattr(chromadb, "__version__", ""))
print("[verify] numpy", getattr(numpy, "__version__", ""))
PY

${PYTHON_BIN} scripts/test_chromadb_py39.py

${PYTHON_BIN} - <<'PY'
from backend.main import app
print("[verify] backend.main:app import ok", bool(app))
PY

echo "[verify] Python 3.9 backend verification passed."
