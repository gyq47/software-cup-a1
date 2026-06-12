# Windows 10 + VS Code Remote WSL 开发与 LoongArch64 Python 3.9 部署说明

本项目主部署路线已调整为：

- 本地开发：Windows 10 + VS Code Remote WSL
- 本地 Python 虚拟环境：`.venv-py39`
- 最终部署：LoongArch64 Docker 容器
- 后端基础镜像：`loongarch64/python:3.9`
- 目标 Python：`3.9.18`
- ChromaDB：`chromadb==0.4.24`

## 1. 本地 WSL 开发流程

不要修改 WSL 系统默认 Python。建议单独创建 `.venv-py39`：

```bash
bash scripts/setup_wsl_py39_dev.sh
source .venv-py39/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

如果 WSL 中没有 `python3.9`，脚本只会提示安装，不会删除或改写系统 Python。

## 2. Python 3.9 主依赖

主依赖文件：

```text
requirements-core-py39.txt
```

关键版本：

- `fastapi==0.110.3`
- `starlette==0.37.2`
- `pydantic==1.10.15`
- `uvicorn==0.39.0`
- `chromadb==0.4.24`
- `pypdf==6.4.1`

不默认安装：

- `torch`
- `sentence-transformers`
- `faiss-cpu`

## 3. LoongArch64 wheels 离线安装

将已验证的 `cp39-cp39-linux_loongarch64` wheels 放入：

```text
wheels/
```

Dockerfile 会使用：

```bash
python -m pip install --find-links=/app/wheels -r requirements-core-py39.txt
```

并设置：

```text
PIP_ONLY_BINARY=chromadb,chroma-hnswlib,onnxruntime,grpcio,tokenizers,orjson,numpy
```

如果这些包没有可用 wheel，构建应失败，而不是在 LoongArch 上重新编译。

## 4. Docker 构建

```bash
docker compose -f docker-compose.loongarch.yml build
```

后端也可以单独构建：

```bash
docker build -f Dockerfile.backend.loongarch.py39 -t software-cup-a1-backend:loongarch-py39 .
```

## 5. Docker 启动

```bash
docker compose -f docker-compose.loongarch.yml up -d
```

访问：

- 后端：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`
- 前端：`http://localhost:5173`

后端启动命令：

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## 6. 默认降级环境变量

当前 LoongArch Python 3.9 主路线默认：

```text
DISABLE_CHROMA=false
DISABLE_LOCAL_EMBEDDING=true
DISABLE_PDF_PREVIEW=true
DISABLE_IMAGE_KNOWLEDGE=true
```

含义：

- ChromaDB 安装并可验证 add/query。
- 本地 HuggingFace embedding 默认禁用，避免 `torch/sentence-transformers`。
- PDF 页截图生成默认禁用。
- PDF 图片知识化默认禁用。

## 7. ChromaDB add/query 验证

容器内或 `.venv-py39` 中执行：

```bash
python scripts/test_chromadb_py39.py
```

完整后端自检：

```bash
bash scripts/verify_py39_backend.sh
```

检查内容：

- Python 版本必须是 `3.9.x`
- `pip check`
- import `fastapi / uvicorn / chromadb / numpy`
- ChromaDB `PersistentClient / collection.add / collection.query`
- `backend.main:app` 可导入

## 8. Python 3.11 项目级残留清理

已处理：

- `Dockerfile.backend.loongarch` 已替换为 Python 3.9 路线。
- 新增 `Dockerfile.backend.loongarch.py39` 作为明确主部署文件。
- `docker-compose.loongarch.yml` 默认使用 `Dockerfile.backend.loongarch.py39`。
- `requirements.txt` 改为引用 `requirements-core-py39.txt`。
- `requirements-core.txt` 改为历史兼容 wrapper。
- 后端 Python 3.10 `X | None` 类型语法已改为 Python 3.9 可解析的 `Optional[...]`。

旧项目虚拟环境 `venv/` 如果存在且不是 Python 3.9，应删除后使用 `.venv-py39`。

## 9. 后续恢复增强能力

在核心服务稳定后再考虑启用：

```bash
python -m pip install -r requirements-rag-optional.txt
python -m pip install -r requirements-extra-optional.txt
```

注意：

- 不要在 LoongArch 上重新编译 `faiss-cpu`、`torch`、`sentence-transformers`。
- 如果需要 PDF 页预览，优先使用已验证 PyMuPDF cp39 LoongArch wheel。
- 如果需要本地 embedding，应先准备可用 LoongArch wheel 或改为云端 embedding。
