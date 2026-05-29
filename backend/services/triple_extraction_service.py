import hashlib
import json
import re
from typing import Any

from openai import OpenAI, OpenAIError

from backend.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from backend.services.graph_service import GraphDataError, load_graph, normalize_device_model, save_graph

ALLOWED_ENTITY_TYPES = {
    "device",
    "alarm",
    "component",
    "fault",
    "cause",
    "solution",
    "risk",
    "parameter",
    "plc_signal",
    "workflow_step",
    "manual",
}
ALLOWED_RELATIONS = {
    "belongs_to",
    "causes",
    "affects",
    "solves",
    "checks",
    "related_to",
    "requires",
    "prevents",
}
ENTITY_TYPE_ALIASES = {
    "故障": "fault",
    "原因": "cause",
    "措施": "solution",
    "风险": "risk",
    "步骤": "workflow_step",
    "设备": "device",
    "报警": "alarm",
    "部件": "component",
    "参数": "parameter",
    "信号": "plc_signal",
    "手册": "manual",
}
RELATION_ALIASES = {
    "导致": "causes",
    "引起": "causes",
    "影响": "affects",
    "解决": "solves",
    "检查": "checks",
    "关联": "related_to",
    "属于": "belongs_to",
    "需要": "requires",
    "预防": "prevents",
}
MAX_ENTITIES = 20
MAX_TRIPLES = 30


def extract_triples_from_text(
    text: str,
    device_model: str | None = None,
    source: str | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    content = text.strip()
    if not content:
        return {"success": False, "entities": [], "triples": [], "warnings": ["文本不能为空"]}
    if not QWEN_API_KEY:
        return {"success": False, "entities": [], "triples": [], "warnings": ["QWEN_API_KEY 未配置，无法调用 LLM 抽取三元组"]}

    try:
        raw_answer = call_llm_for_triples(content, device_model, source, source_type)
        payload = parse_json_payload(raw_answer)
        warnings: list[str] = []
        entities = normalize_entities(payload.get("entities"), device_model, warnings)
        triples = normalize_triples(payload.get("triples"), warnings, build_entity_type_map(entities))
        return {
            "success": True,
            "entities": entities,
            "triples": triples,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "success": False,
            "entities": [],
            "triples": [],
            "warnings": [f"三元组抽取失败：{exc}"],
        }


def commit_triples_to_graph(
    entities: list[dict[str, Any]],
    triples: list[dict[str, Any]],
    device_model: str | None = None,
    source: str | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    graph = load_graph()
    initial_node_count = len(graph["nodes"])
    initial_edge_count = len(graph["edges"])
    normalized_device = normalize_device_model(device_model or "common")
    warnings: list[str] = []
    normalized_entities = normalize_entities(entities, normalized_device, warnings)
    normalized_triples = normalize_triples(triples, warnings, build_entity_type_map(normalized_entities))

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    nodes_by_key = {
        build_node_key(node.get("name", ""), node.get("type", ""), node.get("device_model", "")): node
        for node in graph["nodes"]
    }
    skipped_nodes = 0

    for entity in normalized_entities:
        node_id = stable_node_id(entity["name"], entity["type"], entity["device_model"])
        key = build_node_key(entity["name"], entity["type"], entity["device_model"])
        if key in nodes_by_key or node_id in nodes_by_id:
            skipped_nodes += 1
            continue
        node = {
            "id": node_id,
            "name": entity["name"],
            "type": entity["type"],
            "description": entity.get("description", ""),
            "device_model": entity["device_model"],
            "metadata": {
                **dict(entity.get("metadata") or {}),
                "source": source or "",
                "source_type": source_type or "",
            },
        }
        graph["nodes"].append(node)
        nodes_by_id[node_id] = node
        nodes_by_key[key] = node

    skipped_edges = 0
    edge_ids = {edge["id"] for edge in graph["edges"]}
    entity_lookup = {
        build_node_key(entity["name"], entity["type"], entity["device_model"]): stable_node_id(
            entity["name"],
            entity["type"],
            entity["device_model"],
        )
        for entity in normalized_entities
    }

    for triple in normalized_triples:
        subject_id = find_or_create_node_for_name(
            graph,
            nodes_by_key,
            triple["subject"],
            normalized_device,
            entity_lookup,
            source,
            source_type,
        )
        object_id = find_or_create_node_for_name(
            graph,
            nodes_by_key,
            triple["object"],
            normalized_device,
            entity_lookup,
            source,
            source_type,
        )
        edge_id = stable_edge_id(subject_id, triple["relation"], object_id, normalized_device)
        if edge_id in edge_ids:
            skipped_edges += 1
            merge_edge_metadata(graph, edge_id, triple, source, source_type)
            continue
        graph["edges"].append(
            {
                "id": edge_id,
                "source": subject_id,
                "target": object_id,
                "relation": triple["relation"],
                "weight": float(triple.get("confidence", 0.6)),
                "evidence": triple.get("evidence", ""),
                "source_label": source or "triple_extraction",
                "device_model": normalized_device,
                "metadata": {
                    "source": source or "",
                    "source_type": source_type or "",
                    "confidence": float(triple.get("confidence", 0.6)),
                    "subject": triple["subject"],
                    "object": triple["object"],
                },
            }
        )
        edge_ids.add(edge_id)

    save_graph(graph)
    return {
        "success": True,
        "added_nodes": len(graph["nodes"]) - initial_node_count,
        "added_edges": len(graph["edges"]) - initial_edge_count,
        "skipped_nodes": skipped_nodes,
        "skipped_edges": skipped_edges,
        "warnings": warnings,
    }


def call_llm_for_triples(
    text: str,
    device_model: str | None,
    source: str | None,
    source_type: str | None,
) -> str:
    client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    messages = [
        {
            "role": "system",
            "content": build_triple_system_prompt(),
        },
        {
            "role": "user",
            "content": build_triple_user_prompt(text, device_model, source, source_type),
        },
    ]
    try:
        response = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=messages,
            temperature=0.1,
        )
    except OpenAIError as exc:
        raise RuntimeError("LLM 调用失败") from exc
    answer = response.choices[0].message.content
    if not answer:
        raise RuntimeError("LLM 未返回有效内容")
    return answer


def build_triple_system_prompt() -> str:
    return (
        "你是工业设备检修知识图谱三元组抽取器。"
        "只从给定文本中抽取实体和关系，不得编造文本没有的信息。"
        "输出必须是合法 JSON，不要输出 Markdown、代码块或额外解释。"
        "实体 type 只能从以下集合选择："
        f"{', '.join(sorted(ALLOWED_ENTITY_TYPES))}。"
        "关系 relation 只能从以下集合选择："
        f"{', '.join(sorted(ALLOWED_RELATIONS))}。"
        "优先抽取设备、报警、部件、故障、原因、检查步骤、解决措施、安全风险、参数、PLC信号。"
    )


def build_triple_user_prompt(
    text: str,
    device_model: str | None,
    source: str | None,
    source_type: str | None,
) -> str:
    return (
        f"设备型号：{device_model or 'common'}\n"
        f"来源：{source or ''}\n"
        f"来源类型：{source_type or ''}\n\n"
        f"待抽取文本：\n{text[:4000]}\n\n"
        "请输出 JSON："
        "{"
        '"entities":[{"name":"","type":"fault","description":"","device_model":""}],'
        '"triples":[{"subject":"","relation":"causes","object":"","evidence":"","confidence":0.6}]'
        "}。"
        f"最多输出 {MAX_ENTITIES} 个实体、{MAX_TRIPLES} 条关系。"
    )


def parse_json_payload(raw_answer: str) -> dict[str, Any]:
    text = raw_answer.strip()
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if code_block:
        text = code_block.group(1)
    else:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("LLM 输出 JSON 根对象不是 object")
    return payload


def normalize_entities(value: Any, device_model: str | None, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        warnings.append("entities 字段缺失或不是数组")
        return []
    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    default_device = normalize_device_model(device_model or "common")
    for item in value[:MAX_ENTITIES]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        entity_type = normalize_entity_type(item.get("type"))
        if not entity_type:
            warnings.append(f"已丢弃非法实体类型：{item.get('type')}")
            continue
        current_device = normalize_device_model(str(item.get("device_model") or default_device))
        key = (name, entity_type, current_device)
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            {
                "name": name,
                "type": entity_type,
                "description": str(item.get("description") or ""),
                "device_model": current_device,
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            }
        )
    return entities


def normalize_triples(
    value: Any,
    warnings: list[str],
    entity_types: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        warnings.append("triples 字段缺失或不是数组")
        return []
    triples: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in value[:MAX_TRIPLES]:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "")).strip()
        object_name = str(item.get("object", "")).strip()
        relation = normalize_relation(item.get("relation"))
        if not subject or not object_name or not relation:
            warnings.append(f"已丢弃非法三元组：{item}")
            continue
        subject, relation, object_name = normalize_triple_direction(subject, relation, object_name, entity_types or {})
        key = (subject, relation, object_name)
        if key in seen:
            continue
        seen.add(key)
        triples.append(
            {
                "subject": subject,
                "relation": relation,
                "object": object_name,
                "evidence": str(item.get("evidence") or ""),
                "confidence": normalize_confidence(item.get("confidence")),
            }
        )
    return triples


def normalize_triple_direction(
    subject: str,
    relation: str,
    object_name: str,
    entity_types: dict[str, str],
) -> tuple[str, str, str]:
    subject_type = entity_types.get(subject, "")
    object_type = entity_types.get(object_name, "")
    if relation == "causes" and subject_type == "fault" and object_type == "cause":
        return object_name, relation, subject
    if relation == "solves" and subject_type == "fault" and object_type == "solution":
        return object_name, relation, subject
    if relation == "checks" and subject_type in {"fault", "cause"} and object_type in {"workflow_step", "component", "plc_signal"}:
        return object_name, relation, subject
    return subject, relation, object_name


def build_entity_type_map(entities: list[dict[str, Any]]) -> dict[str, str]:
    return {str(entity.get("name", "")): str(entity.get("type", "")) for entity in entities if entity.get("name")}


def normalize_entity_type(value: Any) -> str:
    text = str(value or "").strip()
    mapped = ENTITY_TYPE_ALIASES.get(text, text)
    return mapped if mapped in ALLOWED_ENTITY_TYPES else ""


def normalize_relation(value: Any) -> str:
    text = str(value or "").strip()
    mapped = RELATION_ALIASES.get(text, text)
    return mapped if mapped in ALLOWED_RELATIONS else ""


def normalize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.6
    return min(max(number, 0.0), 1.0)


def find_or_create_node_for_name(
    graph: dict[str, Any],
    nodes_by_key: dict[tuple[str, str, str], dict[str, Any]],
    name: str,
    device_model: str,
    entity_lookup: dict[tuple[str, str, str], str],
    source: str | None,
    source_type: str | None,
) -> str:
    for (current_name, _current_type, current_device), node in nodes_by_key.items():
        if current_name == name and current_device in {device_model, "common"}:
            return node["id"]

    guessed_type = guess_entity_type(name)
    key = (name, guessed_type, device_model)
    if key in entity_lookup:
        return entity_lookup[key]

    node_id = stable_node_id(name, guessed_type, device_model)
    node = {
        "id": node_id,
        "name": name,
        "type": guessed_type,
        "description": "",
        "device_model": device_model,
        "metadata": {
            "source": source or "",
            "source_type": source_type or "",
            "auto_created_from_triple": True,
        },
    }
    graph["nodes"].append(node)
    nodes_by_key[key] = node
    return node_id


def merge_edge_metadata(
    graph: dict[str, Any],
    edge_id: str,
    triple: dict[str, Any],
    source: str | None,
    source_type: str | None,
) -> None:
    for edge in graph["edges"]:
        if edge.get("id") != edge_id:
            continue
        if not edge.get("evidence") and triple.get("evidence"):
            edge["evidence"] = triple["evidence"]
        metadata = edge.setdefault("metadata", {})
        metadata.setdefault("sources", [])
        source_record = {
            "source": source or "",
            "source_type": source_type or "",
            "confidence": triple.get("confidence", 0.6),
            "evidence": triple.get("evidence", ""),
        }
        if source_record not in metadata["sources"]:
            metadata["sources"].append(source_record)
        return


def stable_node_id(name: str, entity_type: str, device_model: str) -> str:
    digest = hashlib.sha1(f"{name}|{entity_type}|{device_model}".encode("utf-8")).hexdigest()[:12]
    return f"kg_node_{digest}"


def stable_edge_id(source: str, relation: str, target: str, device_model: str) -> str:
    digest = hashlib.sha1(f"{source}|{relation}|{target}|{device_model}".encode("utf-8")).hexdigest()[:12]
    return f"kg_edge_{digest}"


def build_node_key(name: str, entity_type: str, device_model: str) -> tuple[str, str, str]:
    return (str(name).strip(), str(entity_type).strip(), normalize_device_model(str(device_model or "common")))


def guess_entity_type(name: str) -> str:
    text = name.lower()
    if "报警" in text or re.search(r"\b\d{4,6}\b", text):
        return "alarm"
    if "检查" in text or "确认" in text:
        return "workflow_step"
    if "风险" in text or "急停" in text or "安全" in text:
        return "risk"
    if "复位" in text or "处理" in text:
        return "solution"
    if "异常" in text or "未使能" in text or "错误" in text:
        return "cause"
    return "fault"
