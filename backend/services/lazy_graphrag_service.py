from typing import Any

from backend.services.graph_service import expand_neighbors, list_nodes, matches_device

MAX_GRAPH_CONTEXT_LINES = 12


def identify_seed_nodes(
    user_query: str,
    retrieved_contexts: list[dict[str, Any]],
    device_model: str | None = None,
    max_seeds: int = 5,
) -> list[dict[str, Any]]:
    text = build_match_text(user_query, retrieved_contexts)
    if not text.strip():
        return []

    try:
        candidates = list_nodes(device_model)
    except Exception:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    normalized_text = normalize_text(text)
    query_tokens = extract_tokens(user_query)
    for node in candidates:
        name = str(node.get("name", ""))
        description = str(node.get("description", ""))
        node_tokens = extract_tokens(name)
        score = 0
        if name and normalize_text(name) in normalized_text:
            score += len(name) * 10
        if node_tokens and all(token in normalized_text for token in node_tokens[:3]):
            score += len(node_tokens) * 8
        if query_tokens and node_tokens and set(query_tokens) & set(node_tokens):
            score += len(set(query_tokens) & set(node_tokens)) * 5
        for token in split_keywords(name):
            if token and token in normalized_text:
                score += len(token)
        for token in split_keywords(description):
            if token and token in normalized_text:
                score += 1
        if score > 0 and matches_device(node, device_model):
            scored.append((score, node))

    scored.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    seeds: list[dict[str, Any]] = []
    for _score, node in scored:
        dedupe_key = normalize_text(str(node.get("name") or node.get("id") or ""))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        seeds.append(node)
        if len(seeds) >= max_seeds:
            break
    return seeds


def build_lazy_graph_context(
    user_query: str,
    retrieved_contexts: list[dict[str, Any]],
    device_model: str | None = None,
    depth: int = 2,
    max_seeds: int = 5,
) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        seed_nodes = identify_seed_nodes(user_query, retrieved_contexts, device_model, max_seeds=max_seeds)
        if not seed_nodes:
            return {
                "enabled": False,
                "seed_nodes": [],
                "expanded_nodes": [],
                "edges": [],
                "paths": [],
                "graph_context_text": "",
                "warnings": ["未匹配到关联图谱节点"],
            }

        subgraph = expand_neighbors(
            [str(node["id"]) for node in seed_nodes],
            depth=depth,
            relation_types=None,
            device_model=device_model,
        )
        edges = subgraph.get("edges", [])
        expanded_nodes = subgraph.get("nodes", [])
        paths = build_edge_paths(edges, expanded_nodes)
        return {
            "enabled": bool(edges),
            "seed_nodes": seed_nodes,
            "expanded_nodes": expanded_nodes,
            "edges": edges,
            "paths": paths,
            "graph_context_text": format_graph_context_text(edges, expanded_nodes),
            "warnings": warnings if edges else ["图谱命中节点，但未扩展到有效关系"],
        }
    except Exception as exc:
        return {
            "enabled": False,
            "seed_nodes": [],
            "expanded_nodes": [],
            "edges": [],
            "paths": [],
            "graph_context_text": "",
            "warnings": [f"Lazy GraphRAG 降级：{exc}"],
        }


def build_match_text(user_query: str, contexts: list[dict[str, Any]]) -> str:
    context_text = " ".join(str(context.get("content", "")) for context in contexts[:8])
    return f"{user_query} {context_text}"


def build_edge_paths(edges: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node_map = {node["id"]: node for node in nodes}
    paths: list[dict[str, Any]] = []
    for edge in edges[:MAX_GRAPH_CONTEXT_LINES]:
        source = node_map.get(edge.get("source"), {})
        target = node_map.get(edge.get("target"), {})
        paths.append(
            {
                "source": source.get("name", edge.get("source", "")),
                "relation": edge.get("relation", "related_to"),
                "target": target.get("name", edge.get("target", "")),
                "evidence": edge.get("evidence", ""),
                "device_model": edge.get("device_model", ""),
            }
        )
    return paths


def format_graph_context_text(edges: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> str:
    paths = build_edge_paths(edges, nodes)
    if not paths:
        return ""
    lines = ["【关联知识图谱】"]
    for path in paths:
        lines.append(
            f"- {path['source']} --{path['relation']}--> {path['target']}"
            + (f"；依据：{path['evidence']}" if path.get("evidence") else "")
        )
    return "\n".join(lines)


def normalize_text(text: str) -> str:
    return str(text or "").lower().replace(" ", "")


def split_keywords(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [token for token in [normalized] if len(token) >= 2]


def extract_tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in __import__("re").findall(r"[a-zA-Z]+\\d*|\\d+[a-zA-Z]*|[\\u4e00-\\u9fff]{2,}", str(text or ""))
        if len(token.strip()) >= 2
    ]
