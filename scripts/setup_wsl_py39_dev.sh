#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

if ! command -v python3.9 >/dev/null 2>&1; then
  cat <<'MSG'
[WSL Py39] 未找到 python3.9。
请先在 WSL 中安装 Python 3.9，然后重新运行本脚本。
本脚本不会修改系统默认 python，也不会删除系统 Python。
MSG
  exit 1
fi

PYTHON_VERSION="$(python3.9 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "[WSL Py39] detected python ${PYTHON_VERSION}"

python3.9 -m venv .venv-py39
source .venv-py39/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-core-py39.txt

cat <<'MSG'
[WSL Py39] .venv-py39 创建完成。
启用方式：
  source .venv-py39/bin/activate

启动后端：
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
MSG
