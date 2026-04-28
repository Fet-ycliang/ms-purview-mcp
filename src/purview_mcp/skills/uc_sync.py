from __future__ import annotations

import json
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import TableType

from ..client.purview import PurviewClient
from ..models import Settings, UCColumnInfo, UCTableInfo


def _build_databricks_client(settings: Settings) -> WorkspaceClient:
    if settings.databricks_token:
        return WorkspaceClient(
            host=settings.databricks_host,
            token=settings.databricks_token,
        )
    return WorkspaceClient(
        host=settings.databricks_host,
        azure_tenant_id=settings.databricks_tenant_id or settings.azure_tenant_id,
        azure_client_id=settings.databricks_client_id or settings.azure_client_id,
        azure_client_secret=settings.databricks_client_secret or settings.azure_client_secret,
    )


async def list_uc_tables(
    settings: Settings,
    catalog: str | None = None,
    schema_name: str | None = None,
) -> list[UCTableInfo]:
    """列出 Unity Catalog 中的資料表，含 column metadata。"""
    db = _build_databricks_client(settings)
    target_catalog = catalog or settings.uc_default_catalog

    tables: list[UCTableInfo] = []
    for table in db.tables.list(catalog_name=target_catalog, schema_name=schema_name or ""):
        columns = [
            UCColumnInfo(
                name=col.name or "",
                type_text=col.type_text,
                comment=col.comment,
                nullable=col.nullable if col.nullable is not None else True,
            )
            for col in (table.columns or [])
        ]
        tables.append(
            UCTableInfo(
                catalog=table.catalog_name or target_catalog,
                schema=table.schema_name or "",
                table_name=table.name or "",
                table_type=table.table_type.value if table.table_type else None,
                comment=table.comment,
                properties=dict(table.properties or {}),
                columns=columns,
            )
        )
    return tables


async def sync_uc_to_purview(
    settings: Settings,
    catalog: str | None = None,
    schema_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    將 Unity Catalog 的 table metadata 同步到 Purview。

    乾跑 (dry_run=True) 時只回傳要同步的 entity 清單，不實際寫入。
    """
    uc_tables = await list_uc_tables(settings, catalog, schema_name)
    if not uc_tables:
        return {"synced": 0, "tables": []}

    entities = [_uc_table_to_atlas_entity(t, settings) for t in uc_tables]

    if dry_run:
        return {"dry_run": True, "count": len(entities), "entities": entities}

    purview = PurviewClient(settings)
    payload = {"entities": entities}
    result = await purview.upsert_entity(payload)

    return {
        "synced": len(entities),
        "tables": [t.table_name for t in uc_tables],
        "purview_response": result,
    }


def _uc_table_to_atlas_entity(table: UCTableInfo, settings: Settings) -> dict[str, Any]:
    workspace = settings.databricks_host.rstrip("/")
    qualified_name = f"{workspace}/{table.catalog}/{table.schema_name}/{table.table_name}"

    columns = [
        {
            "typeName": "databricks_column",
            "attributes": {
                "name": col.name,
                "qualifiedName": f"{qualified_name}/{col.name}",
                "dataType": col.type_text or "unknown",
                "comment": col.comment or "",
                "isNullable": col.nullable,
            },
        }
        for col in table.columns
    ]

    return {
        "typeName": "databricks_table",
        "attributes": {
            "name": table.table_name,
            "qualifiedName": qualified_name,
            "description": table.comment or "",
            "tableType": table.table_type or "TABLE",
            "userProperties": json.dumps(table.properties),
            "columns": columns,
        },
    }
