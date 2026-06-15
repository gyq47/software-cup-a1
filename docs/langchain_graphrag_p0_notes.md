# LangChain / Lazy GraphRAG P0 Notes

当前基础可交付版本的主流程是 `LangChain RAG pipeline`，入口为
`backend.rag.langchain_pipeline.run_langchain_chat`。它负责 query 解析、RAG 检索、精确匹配合并、
Lazy GraphRAG 上下文构建、Qwen 生成和前端兼容响应组装。

当前没有接入 LangGraph workflow，也没有使用 `StateGraph`、`create_agent` 或 LangChain Agent Tool
调度。LangGraph 后续可以作为可选 workflow 封装现有步骤，但不应在基础可交付版本中替换稳定的
RAG / Lazy GraphRAG 主路径。

`backend.services.lazy_graphrag_service` 当前定位是 `graph_context_builder`：它基于用户问题和已召回
contexts 识别 seed 节点，再扩展知识图谱上下文。它不是 retriever 的替代品，也不应绕过设备型号过滤。

`backend.services.tool_orchestrator_service` 当前更准确地说是 `tool_trace builder`：它把 RAG 检索、
Lazy GraphRAG、诊断生成、作业卡生成、合规校验等已执行步骤包装成前端可展示的工具链轨迹。它目前
不是 LangChain Agent Tool 调度器。

设备型号过滤语义：

- 请求指定 `device_model` 时，最终 contexts 只允许目标设备、无明确设备型号、或 `common/general`
  通用片段。
- 另一个明确设备型号的片段会被 device gate 丢弃，并在 `retrieval_filter.device_gate_dropped_count`
  与 `retrieval_filter.device_gate_dropped_devices` 中保留信息。
- 如果底层检索触发了 `filter_fallback=True`，LangChain pipeline 不应把它覆盖为 `False`。
