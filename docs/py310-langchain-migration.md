# Python 3.10 + LangChain 迁移说明

## 迁移原因

当前 A1 项目已经在 Python 3.9 + ChromaDB 0.4.24 路线上完成了 LoongArch 最小可运行验证，但 LangChain 主线版本已经逐步要求 Python 3.10+。为了把 RAG 主流程迁移到更标准的 LangChain 体系，需要新增 Python 3.10 开发和部署路线。

本迁移不删除 Python 3.9 成果。`requirements-core-py39.txt`、`Dockerfile.backend.loongarch.py39`、`wheels/README.md` 和 LoongArch cp39 验证资料继续保留，用作稳定回滚路线。

## 本地 WSL 迁移方式

1. 安装 Python 3.10.14 或 3.10.13。不要替换系统默认 Python。
2. 在项目根目录创建虚拟环境：

```bash
python3.10 -m venv .venv-py310
source .venv-py310/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-core-py310-langchain.txt
```

3. VS Code 默认解释器已配置为：

```text
${workspaceFolder}/.venv-py310/bin/python
```

4. 本地验证：

```bash
python --version
python -m pip check
python scripts/test_langchain_rag_py310.py --dry-run
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## LangChain 主线变化

新增 `backend/rag/langchain_pipeline.py`，把以下环节收束到一条可测试的主链路：

- LangChain `Document` 对象转换；
- `RecursiveCharacterTextSplitter` 构造；
- Chroma / LangChain Chroma / chromadb adapter 检索；
- 设备型号、报警号、MD 参数、PLC/I/O 关键词解析；
- BM25 / exact keyword boost 融合排序；
- `ChatPromptTemplate` 工业检修 Prompt；
- Qwen 失败时返回降级回答，而不是让 `/api/chat` 返回 500；
- 保留 `contexts`、`evidence_items`、`retrieval_filter`、`graph_context`、`tool_trace`、`degraded`、`model_status`、`llm_status` 等前端字段。

## LoongArch VM 风险

- 当前 VM 已验证的是 cp39 wheels，不能直接用于 Python 3.10。
- cp310 的 ChromaDB、onnxruntime、grpcio、orjson、tokenizers、chroma-hnswlib 等原生依赖仍需在 VM 单独验证。
- `Dockerfile.backend.loongarch.py310.langchain` 默认基于 `a1-python310-loongarch:3.10.14`，该镜像需要先在 VM 上由已验证的 LoongArch Python 3.9 基础环境编译 Python 3.10.14 后固化。
- 如果未来 `loongarch64/python:3.10` 可稳定拉取，可以把 Dockerfile 的 `FROM` 替换为该镜像。
- 不建议回到 `loongarch64/python:3.11`，因为它不是当前验证路线。

## 回滚方式

如果 Python 3.10 + LangChain 在 LoongArch 上遇到原生依赖问题，可以切回 Python 3.9 路线：

```bash
docker build -f Dockerfile.backend.loongarch.py39 -t a1-backend-py39 .
docker run --rm -p 8000:8000 a1-backend-py39
```

Python 3.9 路线保留 `DISABLE_LOCAL_EMBEDDING=true` + ChromaDB 0.4.24 adapter 的可运行能力。

