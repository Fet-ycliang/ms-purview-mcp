from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .models import Settings
from .skills import discovery, glossary, lineage, policy, schema, uc_sync

mcp = FastMCP("Purview", instructions=(
    "提供 Microsoft Purview 資料治理工具，整合 Databricks Unity Catalog。"
    "可搜尋資料資產、追蹤血緣、查詢詞彙規範、檢查 PII 標籤，以及同步 UC metadata。"
))


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def _fmt_ts(ts_ms: int | None) -> str:
    if not ts_ms:
        return "未知"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@mcp.tool()
async def search_data_assets(
    keywords: str,
    limit: int = 10,
    entity_type: Optional[str] = None,
) -> str:
    """
    搜尋 Purview 中的資料資產。

    - keywords: 搜尋關鍵字，如 'customer_order' 或 'cbss user'
    - limit: 回傳筆數上限 (1-50)
    - entity_type: 限定類型，如 'databricks_table'、'databricks_notebook'；
                   未指定時預設搜尋所有 Databricks 相關類型
    """
    results = await discovery.search_assets(_settings(), keywords, limit, entity_type)
    if not results:
        return f"找不到符合 '{keywords}' 的資料資產。"
    lines = [f"找到 {len(results)} 筆結果：\n"]
    for r in results:
        lines.append(f"**{r.name}** ({r.entity_type})")
        lines.append(f"  qualified_name: {r.qualified_name}")
        if r.description:
            lines.append(f"  說明: {r.description}")
        if r.owner:
            lines.append(f"  擁有者: {r.owner}")
        if r.experts:
            lines.append(f"  專家: {', '.join(r.experts)}")
        if r.labels:
            lines.append(f"  標籤: {', '.join(r.labels)}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def get_data_lineage(
    qualified_name: str,
    direction: str = "BOTH",
    entity_type: str = "databricks_table",
    depth: int = 3,
) -> str:
    """
    追蹤資料血緣，查詢上下游影響範圍。

    - qualified_name: Purview 中的唯一識別名稱
    - direction: 'INPUT'（上游來源）、'OUTPUT'（下游影響）或 'BOTH'
    - entity_type: 資產類型，預設 'databricks_table'
    - depth: 追蹤深度 (1-5)
    """
    result = await lineage.get_lineage(_settings(), qualified_name, direction, entity_type, depth)
    lines = [f"血緣分析：`{qualified_name}`\n"]
    if result.upstream:
        lines.append(f"**上游來源 ({len(result.upstream)} 個)：**")
        for node in result.upstream:
            lines.append(f"  - {node.name} ({node.entity_type})")
            if node.qualified_name:
                lines.append(f"    {node.qualified_name}")
    else:
        lines.append("**上游來源：** 無")
    lines.append("")
    if result.downstream:
        lines.append(f"**下游影響 ({len(result.downstream)} 個)：**")
        for node in result.downstream:
            lines.append(f"  - {node.name} ({node.entity_type})")
            if node.qualified_name:
                lines.append(f"    {node.qualified_name}")
    else:
        lines.append("**下游影響：** 無")
    return "\n".join(lines)


@mcp.tool()
async def list_glossary_terms(keyword: str = "") -> str:
    """
    列出企業詞彙表 (Business Glossary) 中的標準術語。

    - keyword: 過濾關鍵字；空白時列出所有術語
    """
    terms = await glossary.list_terms(_settings(), keyword)
    if not terms:
        return "詞彙表為空，或找不到符合的術語。"
    lines = [f"找到 {len(terms)} 個詞彙：\n"]
    for t in terms:
        lines.append(f"**{t.name}**" + (f" ({t.status})" if t.status else ""))
        if t.short_description:
            lines.append(f"  {t.short_description}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def check_field_compliance(field_names: list[str]) -> str:
    """
    檢查 Pydantic/DB 欄位名稱是否符合企業詞彙規範。

    - field_names: 待檢查的欄位名稱清單，如 ['customer_id', 'order_dt']
    """
    result = await glossary.check_compliance(_settings(), field_names)
    lines = ["**欄位詞彙規範檢查結果：**\n"]
    for field, matched in result.items():
        status = f"✓ 符合規範（對應詞彙：{matched}）" if matched else "✗ 未找到對應企業詞彙"
        lines.append(f"  `{field}`: {status}")
    return "\n".join(lines)


@mcp.tool()
async def check_pii_labels(
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> str:
    """
    查詢資料集的敏感標籤與 PII 狀態。

    - qualified_name: Purview 中的唯一識別名稱
    - entity_type: 資產類型，預設 'databricks_table'
    """
    labels = await policy.get_sensitivity_labels(_settings(), qualified_name, entity_type)
    has_pii_flag = any(lbl.is_pii for lbl in labels)

    lines = [f"**敏感標籤查詢：** `{qualified_name}`\n"]
    lines.append(f"PII 風險：{'⚠️ 含有 PII 敏感資料，請注意存取控制' if has_pii_flag else '✓ 未偵測到 PII 標籤'}")
    if labels:
        lines.append("\n**標籤清單：**")
        for lbl in labels:
            pii_flag = " [PII]" if lbl.is_pii else ""
            lines.append(f"  - {lbl.label_name}{pii_flag}")
    else:
        lines.append("\n目前無分類標籤。")
    return "\n".join(lines)


@mcp.tool()
async def sync_unity_catalog(
    catalog: Optional[str] = None,
    schema_name: Optional[str] = None,
    dry_run: bool = True,
) -> str:
    """
    將 Databricks Unity Catalog 的 table metadata 同步到 Purview。

    - catalog: UC catalog 名稱；空白時使用 .env 設定的預設 catalog
    - schema_name: 限定 schema；空白時同步整個 catalog
    - dry_run: True（預設）只預覽，不實際寫入；False 才執行同步
    """
    result = await uc_sync.sync_uc_to_purview(_settings(), catalog, schema_name, dry_run)

    if result.get("dry_run"):
        entities = result.get("entities", [])
        lines = [f"**[乾跑模式] 預覽將同步 {result['count']} 張資料表：**\n"]
        for e in entities[:20]:
            attrs = e.get("attributes", {})
            lines.append(f"  - {attrs.get('qualifiedName', '')}")
        if result["count"] > 20:
            lines.append(f"  ... 以及其他 {result['count'] - 20} 張")
        lines.append("\n設定 dry_run=False 以執行實際同步。")
        return "\n".join(lines)

    tables = result.get("tables", [])
    return (
        f"**同步完成！** 共同步 {result['synced']} 張資料表到 Purview。\n"
        f"資料表清單：{', '.join(tables[:10])}"
        + (f"... 等共 {len(tables)} 張" if len(tables) > 10 else "")
    )


@mcp.tool()
async def get_table_schema(
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> str:
    """
    取回資料表的完整欄位定義（結構描述）。

    - qualified_name: Purview 中的唯一識別名稱
    - entity_type: 資產類型，預設 'databricks_table'
    """
    columns = await schema.get_table_schema(_settings(), qualified_name, entity_type)
    if not columns:
        return f"找不到 `{qualified_name}` 的欄位定義，或該資料表無欄位資料。"

    lines = [f"**欄位定義：** `{qualified_name}`\n", f"共 {len(columns)} 個欄位：\n"]
    lines.append("| # | 欄位名稱 | 型別 | 可空值 | 說明 |")
    lines.append("|---|----------|------|--------|------|")
    for i, col in enumerate(columns, start=1):
        dtype = col.data_type or "-"
        nullable = "✓" if col.is_nullable else ("✗" if col.is_nullable is not None else "-")
        desc = col.description or col.comment or ""
        lines.append(f"| {i} | `{col.name}` | {dtype} | {nullable} | {desc} |")
    return "\n".join(lines)


@mcp.tool()
async def get_table_details(
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> str:
    """
    取回資料表的完整屬性，包含 lastAltered、createdAt、擁有者、description、comment。

    - qualified_name: Purview 中的唯一識別名稱
    - entity_type: 資產類型，預設 'databricks_table'
    """
    details = await schema.get_table_details(_settings(), qualified_name, entity_type)
    lines = [f"**資料表詳情：** `{details['name']}`\n"]
    lines.append(f"- **Catalog / Schema：** {details.get('catalog_name', '-')} / {details.get('schema_name', '-')}")
    lines.append(f"- **表類型：** {details.get('table_type', '-')}")
    lines.append(f"- **說明：** {details.get('description') or details.get('comment') or '（無）'}")
    lines.append(f"- **擁有者：** {details.get('owner') or '未設定'}")
    if details.get('experts'):
        lines.append(f"- **專家：** {', '.join(details['experts'])}")
    lines.append(f"- **最後修改：** {_fmt_ts(details.get('last_altered'))}")
    lines.append(f"- **最後修改者：** {details.get('last_altered_by') or '未知'}")
    lines.append(f"- **建立時間：** {_fmt_ts(details.get('created_at'))}")
    lines.append(f"- **建立者：** {details.get('created_by') or '未知'}")
    if details.get('tags'):
        lines.append(f"- **標籤：** {', '.join(details['tags'])}")
    return "\n".join(lines)


@mcp.tool()
async def find_tables_by_column(
    column_name: str,
    catalog: Optional[str] = None,
    schema_name: Optional[str] = None,
) -> str:
    """
    從 Databricks Unity Catalog 搜尋含有指定欄位名稱的資料表。
    支援部分比對（欄位名稱包含 column_name 即符合）。

    - column_name: 要搜尋的欄位名稱（或部分名稱）
    - catalog: 限定 catalog（預設搜尋 uc_catalogs 所有 catalog）
    - schema_name: 限定 schema（選填）

    注意：此工具直接掃描 Databricks UC，範圍大時需要較長時間。
    """
    matches = await schema.find_tables_by_column(_settings(), column_name, catalog, schema_name)
    if not matches:
        return f"在指定範圍內找不到含有欄位 `{column_name}` 的資料表。"

    lines = [f"**含有欄位 `{column_name}` 的資料表（共 {len(matches)} 張）：**\n"]
    for m in matches:
        lines.append(f"**{m['catalog']}.{m['schema']}.{m['table_name']}**")
        if m.get('comment'):
            lines.append(f"  說明：{m['comment']}")
        for col in m['matching_columns']:
            lines.append(f"  - `{col['name']}` ({col['type'] or '未知型別'})")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
