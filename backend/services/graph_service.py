import json
import uuid
from collections import Counter, deque
from pathlib import Path
from typing import Any

from backend.core.config import KNOWLEDGE_GRAPH_PATH

GRAPH_VERSION = "0.1.0"
DEFAULT_WEIGHT = 1.0


class GraphDataError(RuntimeError):
    pass


def load_graph() -> dict[str, Any]:
    ensure_graph_file()
    try:
        payload = json.loads(KNOWLEDGE_GRAPH_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphDataError(f"知识图谱 JSON 损坏：{exc}") from exc
    if not isinstance(payload, dict):
        raise GraphDataError("知识图谱文件格式错误，根对象必须是 JSON object")
    payload.setdefault("nodes", [])
    payload.setdefault("edges", [])
    payload.setdefault("metadata", {})
    return payload


def save_graph(graph: dict[str, Any]) -> dict[str, Any]:
    validate_graph(graph)
    KNOWLEDGE_GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_GRAPH_PATH.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def list_nodes(device_model: str | None = None) -> list[dict[str, Any]]:
    graph = load_graph()
    return [node for node in graph["nodes"] if matches_device(node, device_model)]


def list_edges(device_model: str | None = None) -> list[dict[str, Any]]:
    graph = load_graph()
    nodes = {node["id"] for node in graph["nodes"] if matches_device(node, device_model)}
    return [
        edge
        for edge in graph["edges"]
        if edge.get("source") in nodes and edge.get("target") in nodes and matches_device(edge, device_model)
    ]


def add_node(node: dict[str, Any]) -> dict[str, Any]:
    graph = load_graph()
    new_node = normalize_node(node)
    if any(existing.get("id") == new_node["id"] for existing in graph["nodes"]):
        raise GraphDataError(f"节点已存在：{new_node['id']}")
    graph["nodes"].append(new_node)
    save_graph(graph)
    return new_node


def add_edge(edge: dict[str, Any]) -> dict[str, Any]:
    graph = load_graph()
    new_edge = normalize_edge(edge)
    node_ids = {node.get("id") for node in graph["nodes"]}
    if new_edge["source"] not in node_ids or new_edge["target"] not in node_ids:
        raise GraphDataError("边的 source 或 target 节点不存在")
    if any(existing.get("id") == new_edge["id"] for existing in graph["edges"]):
        raise GraphDataError(f"边已存在：{new_edge['id']}")
    graph["edges"].append(new_edge)
    save_graph(graph)
    return new_edge


def search_nodes(keyword: str, device_model: str | None = None) -> list[dict[str, Any]]:
    normalized_keyword = normalize_text(keyword)
    nodes = list_nodes(device_model)
    if not normalized_keyword:
        return nodes
    return [
        node
        for node in nodes
        if normalized_keyword in normalize_text(node.get("name", ""))
        or normalized_keyword in normalize_text(node.get("description", ""))
        or normalized_keyword in normalize_text(node.get("id", ""))
        or normalized_keyword in normalize_text(json.dumps(node.get("metadata", {}), ensure_ascii=False))
    ]


def expand_neighbors(
    seed_node_ids: list[str],
    depth: int = 2,
    relation_types: list[str] | None = None,
    device_model: str | None = None,
) -> dict[str, Any]:
    graph = load_graph()
    allowed_nodes = {node["id"]: node for node in graph["nodes"] if matches_device(node, device_model)}
    allowed_edges = [
        edge
        for edge in graph["edges"]
        if edge.get("source") in allowed_nodes
        and edge.get("target") in allowed_nodes
        and matches_device(edge, device_model)
        and (not relation_types or edge.get("relation") in relation_types)
    ]
    adjacency = build_adjacency(allowed_edges)

    visited_nodes: set[str] = set()
    visited_edges: set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    for node_id in seed_node_ids:
        if node_id not in allowed_nodes:
            continue
        visited_nodes.add(node_id)
        queue.append((node_id, 0))

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= max(depth, 0):
            continue
        for edge in adjacency.get(current, []):
            visited_edges.add(edge["id"])
            next_node = edge["target"] if edge["source"] == current else edge["source"]
            if next_node not in visited_nodes:
                visited_nodes.add(next_node)
                queue.append((next_node, current_depth + 1))

    return build_graph_response(
        [allowed_nodes[node_id] for node_id in visited_nodes if node_id in allowed_nodes],
        [edge for edge in allowed_edges if edge["id"] in visited_edges],
    )


def find_paths(
    source: str,
    target: str,
    max_depth: int = 3,
    device_model: str | None = None,
) -> dict[str, Any]:
    graph = load_graph()
    allowed_nodes = {node["id"]: node for node in graph["nodes"] if matches_device(node, device_model)}
    source_id = resolve_node_id(source, allowed_nodes)
    target_id = resolve_node_id(target, allowed_nodes)
    if not source_id or not target_id:
        raise GraphDataError("路径查询的 source 或 target 节点不存在")

    allowed_edges = [
        edge
        for edge in graph["edges"]
        if edge.get("source") in allowed_nodes and edge.get("target") in allowed_nodes and matches_device(edge, device_model)
    ]
    adjacency = build_adjacency(allowed_edges)
    queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque([(source_id, [source_id], [])])
    paths: list[dict[str, Any]] = []

    while queue:
        current, node_path, edge_path = queue.popleft()
        if current == target_id:
            paths.append(
                {
                    "nodes": [allowed_nodes[node_id] for node_id in node_path],
                    "edges": edge_path,
                    "path_text": " -> ".join(allowed_nodes[node_id]["name"] for node_id in node_path),
                }
            )
            continue
        if len(node_path) - 1 >= max_depth:
            continue
        for edge in adjacency.get(current, []):
            next_node = edge["target"] if edge["source"] == current else edge["source"]
            if next_node in node_path:
                continue
            queue.append((next_node, [*node_path, next_node], [*edge_path, edge]))

    return {"paths": paths, "count": len(paths)}


def get_subgraph(keyword: str | None = None, depth: int = 2, device_model: str | None = None) -> dict[str, Any]:
    if keyword:
        seed_nodes = search_nodes(keyword, device_model)
        if not seed_nodes:
            return build_graph_response([], [])
        return expand_neighbors([node["id"] for node in seed_nodes], depth=depth, device_model=device_model)
    return build_graph_response(list_nodes(device_model), list_edges(device_model))


def get_overview() -> dict[str, Any]:
    graph = load_graph()
    nodes = graph["nodes"]
    edges = graph["edges"]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_stats": dict(Counter(str(node.get("type", "unknown")) for node in nodes)),
        "device_model_stats": dict(Counter(str(node.get("device_model", "common") or "common") for node in nodes)),
        "relation_stats": dict(Counter(str(edge.get("relation", "related_to")) for edge in edges)),
        "graph_path": str(KNOWLEDGE_GRAPH_PATH),
        "version": graph.get("metadata", {}).get("version", GRAPH_VERSION),
    }


def build_graph_response(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_ids = {node["id"] for node in nodes}
    visible_edges = [edge for edge in edges if edge.get("source") in node_ids and edge.get("target") in node_ids]
    return {
        "nodes": sorted(nodes, key=lambda item: item.get("name", "")),
        "edges": sorted(visible_edges, key=lambda item: item.get("id", "")),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(visible_edges),
            "node_type_stats": dict(Counter(str(node.get("type", "unknown")) for node in nodes)),
            "relation_stats": dict(Counter(str(edge.get("relation", "related_to")) for edge in visible_edges)),
        },
    }


def ensure_graph_file() -> None:
    if KNOWLEDGE_GRAPH_PATH.exists():
        return
    save_graph(build_initial_graph())


def build_initial_graph() -> dict[str, Any]:
    nodes = [
        node("device_808d", "SINUMERIK 808D", "device", "西门子 808D 数控系统。", "SINUMERIK 808D"),
        node("device_828d", "SINUMERIK 828D", "device", "西门子 828D 数控系统。", "SINUMERIK 828D"),
        node("device_s120", "SINAMICS S120", "device", "828D 常见配套驱动系统。", "SINUMERIK 828D"),
        node("manual_828d_alarm", "828D 报警诊断手册", "manual", "SINUMERIK 828D 报警诊断依据。", "SINUMERIK 828D"),
        node("manual_828d_s120_alarm", "828D S120 报警诊断手册", "manual", "SINAMICS S120 驱动报警诊断依据。", "SINUMERIK 828D"),
        node("fault_axis_ref", "轴无法回零", "fault", "轴不能到达参考点或回参考点失败。", "common"),
        node("fault_spindle", "主轴异常", "fault", "主轴启动、转速、报警或运行状态异常。", "common"),
        node("fault_motor_overheat", "电机过热", "fault", "电机或驱动温度异常升高。", "common"),
        node("cause_ref_switch", "回零开关异常", "cause", "参考点开关、减速凸轮或相关信号异常。", "common"),
        node("cause_plc_input", "PLC 输入信号异常", "cause", "PLC 输入点未按预期变化。", "common"),
        node("cause_servo_enable", "伺服驱动未使能", "cause", "驱动未就绪、未使能或安全链路未闭合。", "common"),
        node("cause_encoder", "编码器异常", "cause", "编码器反馈、连接或参数异常。", "common"),
        node("cause_estop", "急停回路异常", "cause", "急停、安全联锁或安全回路未复位。", "common"),
        node("cause_parameter", "参数设置错误", "cause", "机床数据、轴参数或回零相关参数设置错误。", "common"),
        node("solution_alarm_reset", "报警复位", "solution", "排除故障后执行报警复位并低速验证。", "common"),
        node("risk_power", "停机断电确认", "risk", "检修前执行停机、断电、挂牌和防误启动确认。", "common"),
        node("step_check_ref_switch", "检查回零开关与减速凸轮", "workflow_step", "检查参考点开关动作、线缆和安装位置。", "common"),
        node("step_check_plc", "检查 PLC 输入信号", "workflow_step", "观察 PLC 输入点与诊断界面信号状态。", "common"),
        node("step_check_drive", "检查伺服驱动状态", "workflow_step", "确认驱动就绪、使能、报警和安全状态。", "common"),
        node("step_check_encoder", "检查编码器反馈", "workflow_step", "确认编码器连接、反馈和相关参数。", "common"),
        node("alarm_20000", "报警 20000", "alarm", "808D 参考点相关报警测试节点。", "SINUMERIK 808D"),
        node("alarm_s120_drive", "S120 驱动报警", "alarm", "828D/S120 驱动报警诊断入口。", "SINUMERIK 828D"),
    ]
    edges = [
        edge("e_808d_alarm20000", "alarm_20000", "device_808d", "belongs_to", "808D 报警归属。", "SINUMERIK 808D"),
        edge("e_828d_s120_alarm", "alarm_s120_drive", "device_s120", "belongs_to", "S120 驱动报警归属。", "SINUMERIK 828D"),
        edge("e_s120_828d", "device_s120", "device_828d", "related_to", "S120 与 828D 集成使用。", "SINUMERIK 828D"),
        edge("e_manual_828d_device", "manual_828d_alarm", "device_828d", "belongs_to", "828D 报警诊断手册适用于 828D。", "SINUMERIK 828D"),
        edge("e_manual_s120_device", "manual_828d_s120_alarm", "device_s120", "belongs_to", "S120 报警诊断手册适用于 S120。", "SINUMERIK 828D"),
        edge("e_axis_ref_switch", "cause_ref_switch", "fault_axis_ref", "causes", "回零开关或减速凸轮异常会导致回零失败。", "common"),
        edge("e_axis_plc", "cause_plc_input", "fault_axis_ref", "causes", "PLC 输入信号异常会影响回参考点判断。", "common"),
        edge("e_axis_servo", "cause_servo_enable", "fault_axis_ref", "causes", "伺服未使能时轴无法正常运动。", "common"),
        edge("e_axis_encoder", "cause_encoder", "fault_axis_ref", "causes", "编码器反馈异常会影响位置闭环和参考点。", "common"),
        edge("e_axis_estop", "cause_estop", "fault_axis_ref", "causes", "急停回路异常会阻止轴运动。", "common"),
        edge("e_axis_param", "cause_parameter", "fault_axis_ref", "causes", "回零参数设置错误会导致参考点流程异常。", "common"),
        edge("e_alarm20000_axis", "alarm_20000", "fault_axis_ref", "affects", "报警 20000 与轴参考点问题关联。", "SINUMERIK 808D"),
        edge("e_s120_motor_overheat", "alarm_s120_drive", "fault_motor_overheat", "affects", "S120 驱动报警可关联电机过热。", "SINUMERIK 828D"),
        edge("e_s120_spindle", "alarm_s120_drive", "fault_spindle", "affects", "S120 驱动报警可影响主轴运行。", "SINUMERIK 828D"),
        edge("e_check_ref", "step_check_ref_switch", "cause_ref_switch", "checks", "现场检查参考点开关和减速凸轮。", "common"),
        edge("e_check_plc", "step_check_plc", "cause_plc_input", "checks", "通过 PLC 输入状态排查信号异常。", "common"),
        edge("e_check_drive", "step_check_drive", "cause_servo_enable", "checks", "检查驱动就绪和使能状态。", "common"),
        edge("e_check_encoder", "step_check_encoder", "cause_encoder", "checks", "检查编码器反馈链路。", "common"),
        edge("e_reset_axis", "solution_alarm_reset", "fault_axis_ref", "solves", "故障排除后复位报警并试运行。", "common"),
        edge("e_risk_ref", "risk_power", "step_check_ref_switch", "prevents", "机械和信号检查前必须停机断电。", "common"),
        edge("e_risk_drive", "risk_power", "step_check_drive", "prevents", "驱动检查前确认安全状态。", "common"),
        edge("e_manual_828d_alarm", "manual_828d_alarm", "alarm_s120_drive", "related_to", "828D 报警诊断手册提供报警解释。", "SINUMERIK 828D"),
        edge("e_manual_s120_alarm", "manual_828d_s120_alarm", "alarm_s120_drive", "related_to", "S120 手册提供驱动报警依据。", "SINUMERIK 828D"),
    ]
    return {
        "metadata": {"version": GRAPH_VERSION, "description": "轻量工业检修知识图谱"},
        "nodes": nodes,
        "edges": edges,
    }


def node(node_id: str, name: str, node_type: str, description: str, device_model: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "type": node_type,
        "description": description,
        "device_model": device_model,
        "metadata": {},
    }


def edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    evidence: str,
    device_model: str,
    weight: float = DEFAULT_WEIGHT,
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "weight": weight,
        "evidence": evidence,
        "source_label": "初始化工业检修知识",
        "device_model": device_model,
        "metadata": {},
    }


def normalize_node(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise GraphDataError("节点 name 不能为空")
    return {
        "id": str(payload.get("id") or f"node_{uuid.uuid4().hex[:12]}"),
        "name": name,
        "type": str(payload.get("type") or "fault"),
        "description": str(payload.get("description") or ""),
        "device_model": str(payload.get("device_model") or "common"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def normalize_edge(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("source", "")).strip()
    target = str(payload.get("target", "")).strip()
    if not source or not target:
        raise GraphDataError("边 source 和 target 不能为空")
    return {
        "id": str(payload.get("id") or f"edge_{uuid.uuid4().hex[:12]}"),
        "source": source,
        "target": target,
        "relation": str(payload.get("relation") or "related_to"),
        "weight": float(payload.get("weight") or DEFAULT_WEIGHT),
        "evidence": str(payload.get("evidence") or ""),
        "source_label": str(payload.get("source_label") or payload.get("source") or "manual"),
        "device_model": str(payload.get("device_model") or "common"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def validate_graph(graph: dict[str, Any]) -> None:
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise GraphDataError("知识图谱必须包含 nodes 和 edges 数组")


def build_adjacency(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for current_edge in edges:
        adjacency.setdefault(current_edge["source"], []).append(current_edge)
        adjacency.setdefault(current_edge["target"], []).append(current_edge)
    return adjacency


def resolve_node_id(value: str, nodes: dict[str, dict[str, Any]]) -> str | None:
    normalized = normalize_text(value)
    if value in nodes:
        return value
    for node_id, current_node in nodes.items():
        if normalized in {normalize_text(node_id), normalize_text(current_node.get("name", ""))}:
            return node_id
    return None


def matches_device(item: dict[str, Any], device_model: str | None) -> bool:
    if not device_model:
        return True
    requested = normalize_device_model(device_model)
    current = normalize_device_model(str(item.get("device_model", "")))
    return current in {"common", "", requested}


def normalize_device_model(value: str) -> str:
    upper = value.upper()
    if "808D" in upper:
        return "SINUMERIK 808D"
    if "828D" in upper:
        return "SINUMERIK 828D"
    if "COMMON" in upper:
        return "common"
    return value.strip() or "common"


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")
