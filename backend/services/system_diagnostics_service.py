import os
import platform
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.config import (
    DISABLE_CHROMA,
    DISABLE_PDF_PREVIEW,
    KNOWLEDGE_GRAPH_PATH,
    MANUAL_PAGE_IMAGE_PATH,
    MANUAL_STATIC_PATH,
    MANUAL_UPLOAD_PATH,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_MODEL,
    VECTOR_STORE_PATH,
    VERSION,
)


Status = str


def run_system_diagnostics(deep_check: bool = False) -> dict[str, Any]:
    modules = [
        _safe_check("基础服务", check_base_service),
        _safe_check("Chroma 向量库", check_vector_store),
        _safe_check("手册文件", check_manual_files),
        _safe_check("PDF 页截图", check_page_images),
        _safe_check("知识图谱", check_knowledge_graph),
        _safe_check("Lazy GraphRAG", check_lazy_graphrag),
        _safe_check("Tool Orchestrator", check_tool_orchestrator),
        _safe_check("LLM 配置", lambda: check_llm_config(deep_check=deep_check)),
        _safe_check("LoongArch 部署风险", check_loongarch_risks),
    ]
    return {
        "overall_status": _overall_status(modules),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "version": VERSION,
        "deep_check": deep_check,
        "modules": modules,
        "demo_checklist": build_demo_checklist(modules),
    }


def run_system_health() -> dict[str, Any]:
    diagnostics = run_system_diagnostics(deep_check=False)
    return {
        "overall_status": diagnostics["overall_status"],
        "checked_at": diagnostics["checked_at"],
        "version": VERSION,
        "modules": [
            {
                "name": module["name"],
                "status": module["status"],
                "message": module["message"],
            }
            for module in diagnostics["modules"]
        ],
        "demo_checklist": diagnostics["demo_checklist"],
    }


def check_base_service() -> dict[str, Any]:
    paths = {
        "manual_static_dir": str(MANUAL_STATIC_PATH),
        "manual_upload_dir": str(MANUAL_UPLOAD_PATH),
        "vector_store_dir": str(VECTOR_STORE_PATH),
        "knowledge_graph_path": str(KNOWLEDGE_GRAPH_PATH),
    }
    missing = [name for name, value in paths.items() if not Path(value).exists()]
    return _module(
        "基础服务",
        "warning" if missing else "ok",
        "基础目录存在" if not missing else f"缺少目录或文件：{', '.join(missing)}",
        metrics={
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "backend_version": VERSION,
            **paths,
        },
        warnings=[f"{item} 不存在" for item in missing],
    )


def check_vector_store() -> dict[str, Any]:
    if DISABLE_CHROMA:
        return _module(
            "Chroma 向量库",
            "warning",
            "Chroma 已禁用，系统处于最小部署模式",
            metrics={"vector_store_dir": str(VECTOR_STORE_PATH), "disabled": True, "total_chunks": 0},
            warnings=["DISABLE_CHROMA=true，RAG 向量检索不可用"],
        )

    sqlite_path = VECTOR_STORE_PATH / "chroma.sqlite3"
    if not sqlite_path.exists():
        return _module(
            "Chroma 向量库",
            "error",
            "未找到 Chroma sqlite 索引文件",
            metrics={"vector_store_dir": str(VECTOR_STORE_PATH), "sqlite_path": str(sqlite_path)},
            warnings=["请先执行 /api/manual/rebuild-index 建立索引"],
        )

    with sqlite3.connect(sqlite_path) as connection:
        total_chunks = _safe_sql_count(connection, "select count(*) from embeddings")
        collection_count = _safe_sql_count(connection, "select count(*) from collections")
        device_counts = _count_metadata_values(connection, "device_model")
        source_counts = _count_metadata_values(connection, "source_type")
        manual_type_counts = _count_metadata_values(connection, "manual_type")

    has_808d = any("808D" in key.upper() and value > 0 for key, value in device_counts.items())
    has_828d = any("828D" in key.upper() and value > 0 for key, value in device_counts.items())
    feedback_case_count = source_counts.get("feedback_case", 0)
    warnings = []
    if total_chunks <= 0:
        warnings.append("Chroma collection 中没有 embeddings")
    if not has_808d:
        warnings.append("未检测到 SINUMERIK 808D chunks")
    if not has_828d:
        warnings.append("未检测到 SINUMERIK 828D chunks")
    if feedback_case_count <= 0:
        warnings.append("暂无审核案例 feedback_case 入库记录")

    return _module(
        "Chroma 向量库",
        "warning" if warnings else "ok",
        f"已加载 {total_chunks} 个 chunks" if total_chunks else "向量库为空",
        metrics={
            "vector_store_dir": str(VECTOR_STORE_PATH),
            "sqlite_path": str(sqlite_path),
            "collection_count": collection_count,
            "total_chunks": total_chunks,
            "device_model_counts": device_counts,
            "manual_type_counts": manual_type_counts,
            "source_type_counts": source_counts,
            "has_808d": has_808d,
            "has_828d": has_828d,
            "feedback_case_count": feedback_case_count,
        },
        warnings=warnings,
    )


def check_manual_files() -> dict[str, Any]:
    static_pdfs = list(MANUAL_STATIC_PATH.rglob("*.pdf")) if MANUAL_STATIC_PATH.exists() else []
    upload_pdfs = list(MANUAL_UPLOAD_PATH.rglob("*.pdf")) if MANUAL_UPLOAD_PATH.exists() else []
    all_pdfs = [*static_pdfs, *upload_pdfs]
    counts = {
        "static_pdf_count": len(static_pdfs),
        "upload_pdf_count": len(upload_pdfs),
        "total_pdf_count": len(all_pdfs),
        "808d_pdf_count": _count_paths_containing(all_pdfs, "808D"),
        "828d_pdf_count": _count_paths_containing(all_pdfs, "828D"),
        "manual_static_dir": str(MANUAL_STATIC_PATH),
        "manual_upload_dir": str(MANUAL_UPLOAD_PATH),
    }
    warnings = []
    if counts["total_pdf_count"] <= 0:
        warnings.append("未识别到 PDF 手册")
    if counts["808d_pdf_count"] <= 0:
        warnings.append("未识别到 808D 手册")
    if counts["828d_pdf_count"] <= 0:
        warnings.append("未识别到 828D 手册")
    return _module(
        "手册文件",
        "warning" if warnings else "ok",
        f"识别到 {counts['total_pdf_count']} 本 PDF 手册",
        metrics=counts,
        warnings=warnings,
    )


def check_page_images() -> dict[str, Any]:
    page_image_count = len(list(MANUAL_PAGE_IMAGE_PATH.rglob("*.png"))) if MANUAL_PAGE_IMAGE_PATH.exists() else 0
    dir_size = _directory_size(MANUAL_PAGE_IMAGE_PATH) if MANUAL_PAGE_IMAGE_PATH.exists() else 0
    warnings = []
    if DISABLE_PDF_PREVIEW:
        return _module(
            "PDF 页截图",
            "warning",
            f"PDF 页面预览生成已禁用，现有截图 {page_image_count} 张",
            metrics={
                "manual_pages_dir": str(MANUAL_PAGE_IMAGE_PATH),
                "page_image_count": page_image_count,
                "directory_size_mb": round(dir_size / 1024 / 1024, 2),
                "pymupdf_available": False,
                "disabled": True,
            },
            warnings=["DISABLE_PDF_PREVIEW=true，新的 PDF 页截图不会生成"],
        )

    try:
        import fitz  # noqa: F401

        pymupdf_available = True
    except Exception:
        pymupdf_available = False
        warnings.append("PyMuPDF 不可用，PDF 页面预览生成能力降级")
    if page_image_count <= 0:
        warnings.append("未检测到 PDF 页截图")

    return _module(
        "PDF 页截图",
        "warning" if warnings else "ok",
        f"已生成 {page_image_count} 张页面截图" if page_image_count else "暂无页面截图",
        metrics={
            "manual_pages_dir": str(MANUAL_PAGE_IMAGE_PATH),
            "page_image_count": page_image_count,
            "directory_size_mb": round(dir_size / 1024 / 1024, 2),
            "pymupdf_available": pymupdf_available,
        },
        warnings=warnings,
    )


def check_knowledge_graph() -> dict[str, Any]:
    from backend.services.graph_service import get_overview, get_subgraph, search_nodes

    overview = get_overview()
    axis_nodes = search_nodes("轴无法回零")
    overheat_nodes = search_nodes("电机过热")
    subgraph = get_subgraph("轴无法回零", depth=1)
    warnings = []
    if overview.get("node_count", 0) <= 0:
        warnings.append("知识图谱节点为空")
    if not axis_nodes:
        warnings.append("缺少演示节点：轴无法回零")
    if not overheat_nodes:
        warnings.append("缺少演示节点：电机过热")
    if not subgraph.get("edges"):
        warnings.append("轴无法回零节点未扩展到有效关系")

    return _module(
        "知识图谱",
        "warning" if warnings else "ok",
        f"节点 {overview.get('node_count', 0)} 个，边 {overview.get('edge_count', 0)} 条",
        metrics={
            **overview,
            "axis_ref_node_count": len(axis_nodes),
            "motor_overheat_node_count": len(overheat_nodes),
            "axis_ref_expand_edges": len(subgraph.get("edges", [])),
        },
        warnings=warnings,
    )


def check_lazy_graphrag() -> dict[str, Any]:
    from backend.services.lazy_graphrag_service import build_lazy_graph_context

    graph_context = build_lazy_graph_context("轴无法回零怎么办", [], depth=2)
    enabled = bool(graph_context.get("enabled"))
    warnings = graph_context.get("warnings") or []
    return _module(
        "Lazy GraphRAG",
        "ok" if enabled else "warning",
        "Lazy GraphRAG 可生成局部图谱上下文" if enabled else "未匹配到可用图谱上下文",
        metrics={
            "graph_enabled": enabled,
            "seed_node_count": len(graph_context.get("seed_nodes") or []),
            "path_count": len(graph_context.get("paths") or []),
            "edge_count": len(graph_context.get("edges") or []),
        },
        warnings=warnings,
    )


def check_tool_orchestrator() -> dict[str, Any]:
    from backend.services.tool_orchestrator_service import run_chat_pipeline_trace

    trace = run_chat_pipeline_trace(
        "系统自检",
        [],
        {"used_device_filter": False, "filter_fallback": False},
        {"enabled": False, "seed_nodes": [], "paths": [], "warnings": ["系统自检模拟 trace"]},
    )
    valid = all({"tool_name", "display_name", "status", "duration_ms"}.issubset(item) for item in trace)
    return _module(
        "Tool Orchestrator",
        "ok" if valid else "warning",
        f"工具链 trace 结构正常，包含 {len(trace)} 个步骤" if valid else "工具链 trace 字段不完整",
        metrics={"trace_count": len(trace), "tool_names": [item.get("tool_name") for item in trace]},
        warnings=[] if valid else ["tool_trace 缺少必要字段"],
    )


def check_llm_config(deep_check: bool = False) -> dict[str, Any]:
    warnings = []
    key_configured = bool(QWEN_API_KEY)
    base_configured = bool(QWEN_BASE_URL)
    model_configured = bool(QWEN_MODEL)
    if not key_configured:
        warnings.append("QWEN_API_KEY 未配置")
    if not base_configured:
        warnings.append("QWEN_BASE_URL 未配置")
    if not model_configured:
        warnings.append("QWEN_MODEL 未配置")

    metrics: dict[str, Any] = {
        "api_key_configured": key_configured,
        "base_url": QWEN_BASE_URL,
        "model": QWEN_MODEL,
        "deep_check_executed": deep_check,
    }
    status: Status = "warning" if warnings else "ok"
    message = "LLM 配置已填写" if not warnings else "LLM 配置不完整"

    if deep_check:
        if not (key_configured and base_configured and model_configured):
            warnings.append("配置不完整，跳过模型连通性测试")
        else:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, timeout=8)
                response = client.chat.completions.create(
                    model=QWEN_MODEL,
                    messages=[{"role": "user", "content": "请回复 ok"}],
                    max_tokens=8,
                    temperature=0,
                )
                metrics["deep_check_response"] = bool(response.choices)
                message = "LLM 配置和连通性测试通过"
                status = "ok"
            except Exception as exc:
                warnings.append(f"LLM 连通性测试失败：{exc}")
                status = "warning"
                message = "LLM 配置存在，但连通性测试失败"

    return _module("LLM 配置", status, message, metrics=metrics, warnings=warnings)


def check_loongarch_risks() -> dict[str, Any]:
    package_risks = {
        "torch": _import_available("torch"),
        "sentence_transformers": _import_available("sentence_transformers"),
        "chromadb": _import_available("chromadb"),
        "faiss": _import_available("faiss"),
        "fitz": _import_available("fitz"),
    }
    warnings = [
        f"{name} 当前环境不可导入，银河麒麟/LoongArch 部署时需准备兼容 wheel 或降级方案"
        for name, available in package_risks.items()
        if not available
    ]
    return _module(
        "LoongArch 部署风险",
        "warning" if warnings else "ok",
        "关键依赖当前可导入" if not warnings else "存在需要部署前确认的依赖",
        metrics=package_risks,
        warnings=warnings,
    )


def build_demo_checklist(modules: list[dict[str, Any]]) -> list[dict[str, str]]:
    vector = _find_module(modules, "Chroma 向量库")
    graph = _find_module(modules, "知识图谱")
    lazy = _find_module(modules, "Lazy GraphRAG")
    pages = _find_module(modules, "PDF 页截图")
    llm = _find_module(modules, "LLM 配置")
    vector_metrics = vector.get("metrics", {})
    graph_metrics = graph.get("metrics", {})
    return [
        _check_item("808D 手册已入库", bool(vector_metrics.get("has_808d")), "Chroma 中检测到 808D chunks"),
        _check_item("828D 手册已入库", bool(vector_metrics.get("has_828d")), "Chroma 中检测到 828D chunks"),
        _check_item("图谱节点存在", graph_metrics.get("node_count", 0) > 0, "轻量知识图谱可读取"),
        _check_item("Lazy GraphRAG 可用", lazy.get("status") == "ok", lazy.get("message", "")),
        _check_item("页面截图可预览", pages.get("metrics", {}).get("page_image_count", 0) > 0, "PDF 页截图已生成"),
        _check_item("LLM 已配置", bool(llm.get("metrics", {}).get("api_key_configured")), "默认不执行真实模型调用"),
        _check_item(
            "feedback_case 可用",
            vector_metrics.get("feedback_case_count", 0) > 0,
            f"feedback_case chunks: {vector_metrics.get('feedback_case_count', 0)}",
            warning_when_false=True,
        ),
        _check_item(
            "fallback 风险",
            not vector.get("warnings"),
            "存在 warning 时演示前建议先处理索引或依赖问题",
            warning_when_false=True,
        ),
    ]


def _module(
    name: str,
    status: Status,
    message: str,
    metrics: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "metrics": metrics or {},
        "warnings": warnings or [],
    }


def _safe_check(name: str, checker: Any) -> dict[str, Any]:
    try:
        return checker()
    except Exception as exc:
        return _module(name, "error", f"{name} 检查失败", warnings=[str(exc)])


def _overall_status(modules: list[dict[str, Any]]) -> str:
    statuses = [module.get("status") for module in modules]
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _safe_sql_count(connection: sqlite3.Connection, query: str) -> int:
    value = connection.execute(query).fetchone()
    return int(value[0]) if value else 0


def _count_metadata_values(connection: sqlite3.Connection, key: str) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT COALESCE(string_value, int_value, float_value, bool_value, '') AS value, COUNT(*)
        FROM embedding_metadata
        WHERE key = ?
        GROUP BY value
        """,
        (key,),
    ).fetchall()
    return {str(value or "unknown"): int(count) for value, count in rows}


def _count_paths_containing(paths: list[Path], token: str) -> int:
    normalized = token.lower()
    return sum(1 for path in paths if normalized in str(path).lower())


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _import_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _find_module(modules: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((module for module in modules if module.get("name") == name), {})


def _check_item(name: str, passed: bool, message: str, warning_when_false: bool = False) -> dict[str, str]:
    return {
        "name": name,
        "status": "ok" if passed else ("warning" if warning_when_false else "error"),
        "message": message,
    }
