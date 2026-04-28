from __future__ import annotations

from typing import Any

from databricks.sdk import WorkspaceClient

from ..client.purview import get_purview_client
from ..models import AssetResult, ColumnDef, Settings
from .uc_sync import _build_databricks_client


async def get_table_schema(
    settings: Settings,
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> list[ColumnDef]:
    """從 Purview 取回資料表的完整欄位定義（結構描述）。"""
    client = get_purview_client(settings)

    entity_data = await client.get_entity_by_qualified_name(qualified_name, entity_type)
    entity = entity_data.get("entity", {})
    rel_attrs = entity.get("relationshipAttributes", {})

    col_refs: list[dict] = rel_attrs.get("columns", [])
    if not col_refs:
        return []

    guids = [ref["guid"] for ref in col_refs if ref.get("guid")]
    if not guids:
        return []

    # Bulk 查所有欄位 entity
    bulk_data = await client.get_entities_bulk(guids)
    entities: dict[str, dict] = bulk_data.get("entities", {})
    if isinstance(entities, list):
        entities = {e["guid"]: e for e in entities}

    columns: list[ColumnDef] = []
    for guid in guids:
        col_entity = entities.get(guid, {})
        attrs = col_entity.get("attributes", {})
        columns.append(ColumnDef(
            name=attrs.get("name", ""),
            data_type=attrs.get("dataType"),
            description=attrs.get("description") or attrs.get("userDescription"),
            is_nullable=attrs.get("isNullable"),
            ordinal_position=attrs.get("ordinalPosition"),
            comment=attrs.get("comment"),
            guid=guid,
        ))

    columns.sort(key=lambda c: c.ordinal_position or 0)
    return columns


async def get_table_details(
    settings: Settings,
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> dict[str, Any]:
    """取回資料表的完整屬性，包含 lastAltered、createdAt、owner、description 等。"""
    client = get_purview_client(settings)
    entity_data = await client.get_entity_by_qualified_name(qualified_name, entity_type)
    entity = entity_data.get("entity", {})
    attrs = entity.get("attributes", {})
    contacts = entity.get("contacts", {})

    owners = [c["id"] for c in contacts.get("Owner", []) if c.get("id")]
    experts = [c["id"] for c in contacts.get("Expert", []) if c.get("id")]

    return {
        "name": attrs.get("name", ""),
        "qualified_name": attrs.get("qualifiedName", ""),
        "description": attrs.get("description") or attrs.get("userDescription"),
        "comment": attrs.get("comment"),
        "table_type": attrs.get("tableType"),
        "catalog_name": attrs.get("catalogName"),
        "schema_name": attrs.get("schemaName"),
        "last_altered": attrs.get("lastAltered"),
        "last_altered_by": attrs.get("lastAlteredBy"),
        "created_at": attrs.get("createdAt"),
        "created_by": attrs.get("createdBy"),
        "owner": owners[0] if owners else attrs.get("owner"),
        "experts": experts,
        "tags": attrs.get("tags", []),
    }


async def find_tables_by_column(
    settings: Settings,
    column_name: str,
    catalog: str | None = None,
    schema_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    從 Databricks Unity Catalog 搜尋含有指定欄位名稱的資料表。

    由於 Purview 不索引欄位名稱，改由 UC SDK 直接掃描。
    支援部分比對（column_name 為子字串即符合）。
    """
    db = _build_databricks_client(settings)
    target_catalogs = [catalog] if catalog else settings.uc_catalogs

    matches: list[dict[str, Any]] = []
    search_term = column_name.lower()

    for target_catalog in target_catalogs:
        schemas = (
            [schema_name]
            if schema_name
            else [s.name for s in db.schemas.list(catalog_name=target_catalog) if s.name]
        )
        for schema in schemas:
            for table in db.tables.list(catalog_name=target_catalog, schema_name=schema):
                matching_cols = [
                    {"name": col.name, "type": col.type_text}
                    for col in (table.columns or [])
                    if col.name and search_term in col.name.lower()
                ]
                if matching_cols:
                    matches.append({
                        "table_name": table.name,
                        "catalog": target_catalog,
                        "schema": schema,
                        "qualified_name": f"databricks://{settings.databricks_host.rstrip('/')}/catalogs/{target_catalog}/schemas/{schema}/tables/{table.name}",
                        "matching_columns": matching_cols,
                        "comment": table.comment,
                    })

    return matches
