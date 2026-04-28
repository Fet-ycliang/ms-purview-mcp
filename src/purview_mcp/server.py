from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .models import Settings
from .skills import discovery, glossary, lineage, policy, uc_sync

mcp = FastMCP("Purview", instructions=(
    "提供 Microsoft Purview 資料治理工具，整合 Databricks Unity Catalog。"
    "可搜尋資料資產、追蹤血緣、查詢詞彙規範、檢查 PII 標籤，以及同步 UC metadata。"
))


@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
