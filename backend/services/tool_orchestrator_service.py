import time
from typing import Any, Callable


def build_tool_result(
    tool_name: str,
    display_name: str,
    status: str,
    input_summary: str = "",
    output_summary: str = "",
    duration_ms: int = 0,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "display_name": display_name,
        "status": status,
        "input_summary": input_summary,
        "output_summary": output_summary,
        "duration_ms": duration_ms,
        "error": error,
        "metadata": metadata or {},
    }


def measure_tool(
    tool_name: str,
    display_name: str,
    function: Callable[[], Any],
    input_summary: str = "",
    output_builder: Callable[[Any], tuple[str, dict[str, Any]]] | None = None,
    required: bool = False,
) -> tuple[Any, dict[str, Any]]:
    started_at = time.perf_counter()
    try:
        output = function()
        output_summary, metadata = output_builder(output) if output_builder else ("执行完成", {})
        return output, build_tool_result(
            tool_name=tool_name,
            display_name=display_name,
            status="success",
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=elapsed_ms(started_at),
            metadata=metadata,
        )
    except Exception as exc:
        result = build_tool_result(
            tool_name=tool_name,
            display_name=display_name,
            status="failed",
            input_summary=input_summary,
            output_summary="工具执行失败",
            duration_ms=elapsed_ms(started_at),
            error=str(exc),
        )
        if required:
            raise
        return None, result


def run_vision_analysis_tool(has_image: bool, vision_result: dict[str, Any] | None = None) -> dict[str, Any]:
    if not has_image:
        return build_tool_result(
            "VisionAnalysisTool",
            "多模态视觉识别工具",
            "skipped",
            output_summary="未上传图片，跳过视觉识别",
        )
    vision_result = vision_result or {}
    codes = vision_result.get("fault_codes") or vision_result.get("confirmed_alarm_codes") or []
    parts = vision_result.get("visible_parts") or []
    return build_tool_result(
        "VisionAnalysisTool",
        "多模态视觉识别工具",
        "success",
        output_summary=f"识别报警 {len(codes)} 个，可见部件 {len(parts)} 个",
        metadata={
            "fault_codes": codes,
            "visible_parts_count": len(parts),
            "risk_level": vision_result.get("risk_level", ""),
        },
    )


def run_rag_retrieval_tool(
    query: str,
    contexts: list[dict[str, Any]],
    retrieval_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retrieval_filter = retrieval_filter or {}
    fallback = bool(retrieval_filter.get("filter_fallback", False))
    device = retrieval_filter.get("requested_device_model") or "未指定"
    status = "success" if contexts else "skipped"
    return build_tool_result(
        "RagRetrievalTool",
        "知识检索工具",
        status,
        input_summary=truncate(query),
        output_summary=f"召回 {len(contexts)} 条依据，设备过滤：{device}，{'触发 fallback' if fallback else '未触发 fallback'}",
        metadata={
            "context_count": len(contexts),
            "used_device_filter": bool(retrieval_filter.get("used_device_filter", False)),
            "filter_fallback": fallback,
            "filter_message": retrieval_filter.get("filter_message", ""),
        },
    )


def run_lazy_graphrag_tool(graph_context: dict[str, Any] | None = None) -> dict[str, Any]:
    graph_context = graph_context or {}
    enabled = bool(graph_context.get("enabled", False))
    seed_count = len(graph_context.get("seed_nodes") or [])
    path_count = len(graph_context.get("paths") or [])
    warnings = graph_context.get("warnings") or []
    return build_tool_result(
        "LazyGraphRAGTool",
        "关联图谱扩展工具",
        "success" if enabled else "skipped",
        output_summary=f"seed 节点 {seed_count} 个，关联路径 {path_count} 条" if enabled else (warnings[0] if warnings else "未匹配图谱节点"),
        metadata={
            "graph_enabled": enabled,
            "seed_count": seed_count,
            "path_count": path_count,
            "warnings": warnings,
        },
    )


def run_diagnosis_generation_tool(diagnosis: dict[str, Any] | None = None) -> dict[str, Any]:
    diagnosis = diagnosis or {}
    return build_tool_result(
        "DiagnosisGenerationTool",
        "诊断报告生成工具",
        "success" if diagnosis else "skipped",
        output_summary=truncate(str(diagnosis.get("summary") or "已生成诊断结果")),
        metadata={"risk_level": diagnosis.get("risk_level", ""), "workflow_recommended": diagnosis.get("workflow_recommended", False)},
    )


def run_workflow_generation_tool(workflow: dict[str, Any] | None = None, level: str | None = None) -> dict[str, Any]:
    workflow = workflow or {}
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    return build_tool_result(
        "WorkflowGenerationTool",
        "标准作业卡生成工具",
        "success" if workflow else "skipped",
        output_summary=f"生成作业步骤 {len(steps)} 步，检修等级：{level or '未指定'}",
        metadata={"step_count": len(steps), "level": level or ""},
    )


def run_compliance_check_tool(compliance_result: dict[str, Any] | None = None) -> dict[str, Any]:
    if compliance_result is None:
        return build_tool_result(
            "ComplianceCheckTool",
            "合规校验工具",
            "skipped",
            output_summary="当前流程未执行合规校验",
        )
    warnings = compliance_result.get("warnings") if isinstance(compliance_result.get("warnings"), list) else []
    return build_tool_result(
        "ComplianceCheckTool",
        "合规校验工具",
        "success",
        output_summary=f"{'校验通过' if compliance_result.get('passed') else '发现合规风险'}，风险 {len(warnings)} 条",
        metadata={
            "passed": bool(compliance_result.get("passed", False)),
            "warning_count": len(warnings),
            "summary": compliance_result.get("summary", ""),
        },
    )


def run_feedback_index_tool(index_result: dict[str, Any] | None = None) -> dict[str, Any]:
    index_result = index_result or {}
    indexed = bool(index_result.get("rag_indexed") or index_result.get("indexed"))
    return build_tool_result(
        "FeedbackIndexTool",
        "审核案例入库工具",
        "success" if indexed else "failed",
        output_summary=index_result.get("index_message") or index_result.get("message") or "审核案例索引状态未知",
        error=None if indexed else index_result.get("index_message", ""),
        metadata={"indexed": indexed, "case_id": index_result.get("case_id", "")},
    )


def run_triple_extraction_tool(auto_enabled: bool = False) -> dict[str, Any]:
    return build_tool_result(
        "TripleExtractionTool",
        "候选三元组抽取工具",
        "skipped" if not auto_enabled else "success",
        output_summary="自动三元组抽取未启用，需人工在知识图谱页面触发",
    )


def run_chat_pipeline_trace(
    query: str,
    contexts: list[dict[str, Any]],
    retrieval_filter: dict[str, Any],
    graph_context: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        run_rag_retrieval_tool(query, contexts, retrieval_filter),
        run_lazy_graphrag_tool(graph_context),
    ]


def run_diagnosis_pipeline_trace(
    has_image: bool,
    query: str,
    vision_result: dict[str, Any],
    contexts: list[dict[str, Any]],
    retrieval_filter: dict[str, Any],
    graph_context: dict[str, Any],
    diagnosis: dict[str, Any],
    compliance_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        run_vision_analysis_tool(has_image, vision_result),
        run_rag_retrieval_tool(query, contexts, retrieval_filter),
        run_lazy_graphrag_tool(graph_context),
        run_diagnosis_generation_tool(diagnosis),
        run_compliance_check_tool(compliance_result),
    ]


def run_workflow_pipeline_trace(
    task: str,
    contexts: list[dict[str, Any]],
    retrieval_filter: dict[str, Any],
    graph_context: dict[str, Any],
    workflow: dict[str, Any],
    compliance_result: dict[str, Any],
    level: str | None = None,
) -> list[dict[str, Any]]:
    return [
        run_rag_retrieval_tool(task, contexts, retrieval_filter),
        run_lazy_graphrag_tool(graph_context),
        run_workflow_generation_tool(workflow, level),
        run_compliance_check_tool(compliance_result),
    ]


def run_feedback_pipeline_trace(review_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        build_tool_result(
            "CaseCreationTool",
            "知识案例生成工具",
            "success" if review_result.get("case_id") else "skipped",
            output_summary=f"生成案例：{review_result.get('case_id', '无')}",
            metadata={"case_id": review_result.get("case_id", "")},
        ),
        run_feedback_index_tool(review_result),
        run_triple_extraction_tool(auto_enabled=False),
    ]


def elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def truncate(text: str, max_chars: int = 120) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}..."
