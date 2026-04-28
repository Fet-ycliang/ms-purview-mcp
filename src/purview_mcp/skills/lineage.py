from __future__ import annotations

from ..client.purview import get_purview_client
from ..models import LineageNode, LineageResult, Settings


async def get_lineage(
    settings: Settings,
    qualified_name: str,
    direction: str = "BOTH",
    entity_type: str = "databricks_table",
    depth: int = 3,
) -> LineageResult:
    """取得指定資產的上下游血緣關係。"""
    client = get_purview_client(settings)

    entity_data = await client.get_entity_by_qualified_name(qualified_name, entity_type)
    guid = entity_data.get("entity", {}).get("guid", "")

    lineage_data = await client.get_lineage(guid, direction, depth)

    relations = lineage_data.get("relations", [])
    entities = lineage_data.get("guidEntityMap", {})

    upstream: list[LineageNode] = []
    downstream: list[LineageNode] = []

    for rel in relations:
        from_guid = rel.get("fromEntityId", "")
        to_guid = rel.get("toEntityId", "")

        if to_guid == guid and from_guid in entities:
            upstream.append(_to_node(from_guid, entities[from_guid]))
        elif from_guid == guid and to_guid in entities:
            downstream.append(_to_node(to_guid, entities[to_guid]))

    return LineageResult(
        base_entity_guid=guid,
        upstream=upstream,
        downstream=downstream,
    )


def _to_node(guid: str, entity: dict) -> LineageNode:
    attrs = entity.get("attributes", {})
    return LineageNode(
        guid=guid,
        name=attrs.get("name", guid),
        entity_type=entity.get("typeName", ""),
        qualified_name=attrs.get("qualifiedName"),
    )
