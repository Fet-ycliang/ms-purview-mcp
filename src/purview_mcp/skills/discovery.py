from __future__ import annotations

from ..client.purview import PurviewClient
from ..models import AssetResult, Settings

_DATABRICKS_TYPES = [
    "databricks_table",
    "databricks_notebook",
    "databricks_job",
    "databricks_schema",
]


async def search_assets(
    settings: Settings,
    keywords: str,
    limit: int = 10,
    entity_type: str | None = None,
) -> list[AssetResult]:
    """搜尋 Purview 資料資產，entity_type 未指定時預設搜尋所有 Databricks 類型。"""
    client = PurviewClient(settings)

    if entity_type:
        raw = await client.search(keywords, limit, entity_type)
        return [_to_asset(item) for item in raw]

    # 依序搜尋各 Databricks 類型，合計至 limit
    results: list[AssetResult] = []
    per_type = max(1, limit // len(_DATABRICKS_TYPES))
    for dtype in _DATABRICKS_TYPES:
        if len(results) >= limit:
            break
        items = await client.search(keywords, per_type, dtype)
        results.extend(_to_asset(item) for item in items)

    return results[:limit]


def _to_asset(item: dict) -> AssetResult:
    attrs = item.get("attributes", {})
    return AssetResult(
        name=item.get("name") or attrs.get("name", ""),
        qualified_name=item.get("qualifiedName") or attrs.get("qualifiedName", ""),
        entity_type=item.get("entityType", ""),
        guid=item.get("id"),
        description=item.get("description") or attrs.get("description"),
        labels=item.get("label", []),
    )
