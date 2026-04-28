from __future__ import annotations

from ..client.purview import get_purview_client
from ..models import GlossaryTerm, Settings


async def list_terms(
    settings: Settings,
    keyword: str = "",
) -> list[GlossaryTerm]:
    """列出企業詞彙表，支援關鍵字過濾。"""
    client = get_purview_client(settings)

    glossaries = await client.get_glossary()
    if not glossaries:
        return []

    # 取第一個 glossary（企業通常只有一個主要詞彙表）
    glossary_guid = glossaries[0].get("guid", "")
    terms_raw = await client.get_glossary_terms(glossary_guid)

    terms = [_to_term(t) for t in terms_raw]
    if keyword:
        kw = keyword.lower()
        terms = [t for t in terms if kw in t.name.lower() or kw in (t.short_description or "").lower()]

    return terms


async def check_compliance(
    settings: Settings,
    field_names: list[str],
) -> dict[str, str | None]:
    """檢查欄位名稱是否符合企業詞彙規範，回傳 {field: matched_term | None}。"""
    all_terms = await list_terms(settings)
    term_names = {t.name.lower(): t.name for t in all_terms}

    result: dict[str, str | None] = {}
    for field in field_names:
        normalized = field.lower().replace("_", "").replace("-", "")
        matched = next(
            (official for term_lower, official in term_names.items()
             if normalized in term_lower or term_lower in normalized),
            None,
        )
        result[field] = matched
    return result


def _to_term(raw: dict) -> GlossaryTerm:
    return GlossaryTerm(
        name=raw.get("name", ""),
        guid=raw.get("guid"),
        short_description=raw.get("shortDescription"),
        long_description=raw.get("longDescription"),
        status=raw.get("status"),
        examples=raw.get("examples", []),
    )
