from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.graph_service import (
    GraphDataError,
    add_edge,
    add_node,
    expand_neighbors,
    find_paths,
    get_overview,
    get_subgraph,
    search_nodes,
)
from backend.services.triple_extraction_service import commit_triples_to_graph, extract_triples_from_text

router = APIRouter(prefix="/graph", tags=["graph"])


def dump_model(model: BaseModel, **kwargs: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


class GraphNodeRequest(BaseModel):
    id: Optional[str] = None
    name: str
    type: str = "fault"
    description: str = ""
    device_model: str = "common"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeRequest(BaseModel):
    id: Optional[str] = None
    source: str
    target: str
    relation: str = "related_to"
    weight: float = 1.0
    evidence: str = ""
    source_label: str = "manual"
    device_model: str = "common"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TripleExtractionRequest(BaseModel):
    text: str
    device_model: Optional[str] = None
    source: Optional[str] = None
    source_type: Optional[str] = None


class TripleCommitRequest(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)
    triples: list[dict[str, Any]] = Field(default_factory=list)
    device_model: Optional[str] = None
    source: Optional[str] = None
    source_type: Optional[str] = None


@router.get("/overview")
def graph_overview() -> dict[str, Any]:
    return handle_graph_call(get_overview)


@router.get("/search")
def graph_search(
    keyword: str = Query(default=""),
    device_model: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    nodes = handle_graph_call(search_nodes, keyword, device_model)
    return {"nodes": nodes, "total": len(nodes)}


@router.get("/expand")
def graph_expand(
    node_id: str = Query(...),
    depth: int = Query(default=2, ge=1, le=5),
    device_model: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    result = handle_graph_call(expand_neighbors, [node_id], depth, None, device_model)
    if not result["nodes"]:
        raise HTTPException(status_code=404, detail="节点不存在或无可扩展邻居")
    return result


@router.get("/path")
def graph_path(
    source: str = Query(...),
    target: str = Query(...),
    max_depth: int = Query(default=3, ge=1, le=6),
    device_model: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    return handle_graph_call(find_paths, source, target, max_depth, device_model)


@router.get("/subgraph")
def graph_subgraph(
    keyword: Optional[str] = Query(default=None),
    depth: int = Query(default=2, ge=1, le=5),
    device_model: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    return handle_graph_call(get_subgraph, keyword, depth, device_model)


@router.post("/node")
def graph_add_node(request: GraphNodeRequest) -> dict[str, Any]:
    node = handle_graph_call(add_node, dump_model(request, exclude_none=True))
    return {"success": True, "node": node}


@router.post("/edge")
def graph_add_edge(request: GraphEdgeRequest) -> dict[str, Any]:
    edge = handle_graph_call(add_edge, dump_model(request, exclude_none=True))
    return {"success": True, "edge": edge}


@router.post("/extract-triples")
def graph_extract_triples(request: TripleExtractionRequest) -> dict[str, Any]:
    return extract_triples_from_text(
        text=request.text,
        device_model=request.device_model,
        source=request.source,
        source_type=request.source_type,
    )


@router.post("/commit-triples")
def graph_commit_triples(request: TripleCommitRequest) -> dict[str, Any]:
    return handle_graph_call(
        commit_triples_to_graph,
        request.entities,
        request.triples,
        request.device_model,
        request.source,
        request.source_type,
    )


def handle_graph_call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except GraphDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
