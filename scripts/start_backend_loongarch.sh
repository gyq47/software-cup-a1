#!/usr/bin/env bash
set -euo pipefail

export DISABLE_CHROMA="${DISABLE_CHROMA:-true}"
export DISABLE_PDF_PREVIEW="${DISABLE_PDF_PREVIEW:-true}"
export DISABLE_IMAGE_KNOWLEDGE="${DISABLE_IMAGE_KNOWLEDGE:-true}"
export DISABLE_LOCAL_EMBEDDING="${DISABLE_LOCAL_EMBEDDING:-true}"

mkdir -p \
  backend/data/knowledge_graph \
  backend/data/cases \
  backend/data/feedback \
  backend/data/manuals \
  backend/data/vector_store \
  backend/data/manual_pages \
  uploads/manuals

echo "[LoongArch] backend minimal mode"
echo "[LoongArch] DISABLE_CHROMA=${DISABLE_CHROMA}"
echo "[LoongArch] DISABLE_PDF_PREVIEW=${DISABLE_PDF_PREVIEW}"
echo "[LoongArch] DISABLE_IMAGE_KNOWLEDGE=${DISABLE_IMAGE_KNOWLEDGE}"
echo "[LoongArch] DISABLE_LOCAL_EMBEDDING=${DISABLE_LOCAL_EMBEDDING}"

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
