from __future__ import annotations

import re
from ..client.purview import get_purview_client
from ..models import GlossaryTerm, Settings, FieldComplianceResult


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


def _infer_suggestion(field_name: str) -> str | None:
    """根據欄位名稱推斷建議的標準命名。"""
    # 移除前綴（sys_, dl_, new_, l3_）
    cleaned = field_name
    for prefix in ["sys_", "dl_", "new_", "l3_"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # 展開常見縮寫 - 按優先順序（較長的先）
    abbreviations = [
        ("cust_sub_type", "customer_subscription_type"),
        ("cust_sub", "customer_subscription"),
        ("cust", "customer"),
        ("sub_type", "subscription_type"),
        ("bill_cyc_prod_freq", "bill_cycle_product_frequency"),
        ("cyc_prod_freq", "cycle_product_frequency"),
        ("cyc_req", "cycle_request"),
        ("cyc", "cycle"),
        ("freq", "frequency"),
        ("prod", "product"),
        ("req", "request"),
        ("sts", "status"),
        ("dflt", "default"),
        ("chg", "change"),
        ("conv", "conversion"),
        ("lmt", "limit"),
        ("notif", "notification"),
        ("nofif", "notification"),
        ("crd", "credit"),
        ("dt", "date"),
        ("yr", "year"),
        ("mo", "month"),
        ("ind", "indicator"),
        ("no", "number"),
        ("pcn", "percentage"),
        ("pre", "previous"),
        ("post", "post"),
        ("run", "run"),
    ]

    # 使用下劃線為邊界的正則替換
    suggestion = cleaned
    changed = False
    for abbr, full in abbreviations:
        # 替換形式：_abbr_ 或 abbr_ 或 _abbr
        patterns = [
            (f"_{abbr}_", f"_{full}_"),
            (f"^{abbr}_", f"{full}_"),
            (f"_{abbr}$", f"_{full}"),
            (f"^{abbr}$", full),
        ]
        for pattern, replacement in patterns:
            if pattern.startswith('^'):
                # 開始位置
                if suggestion.startswith(abbr + "_"):
                    suggestion = full + suggestion[len(abbr):]
                    changed = True
            elif pattern.endswith('$'):
                # 結束位置
                if suggestion.endswith("_" + abbr):
                    suggestion = suggestion[:-len(abbr)] + full
                    changed = True
            else:
                # 中間位置
                if f"_{abbr}_" in suggestion:
                    suggestion = suggestion.replace(f"_{abbr}_", f"_{full}_")
                    changed = True

    return suggestion if changed else None


async def check_field_compliance_detailed(
    settings: Settings,
    field_names: list[str],
) -> list[FieldComplianceResult]:
    """
    檢查欄位名稱是否符合企業詞彙規範。

    回傳包含 compliant、suggestion 和 matched_term 的詳細結果清單。
    """
    all_terms = await list_terms(settings)
    term_names_lower = {t.name.lower(): t.name for t in all_terms}

    results = []

    for field in field_names:
        normalized = field.lower().replace("_", "").replace("-", "")

        # 尋找匹配的詞彙
        matched_term = None
        for term_lower, official in term_names_lower.items():
            if normalized in term_lower or term_lower in normalized:
                matched_term = official
                break

        # 判定是否符合規範
        compliant = matched_term is not None

        # 生成建議
        suggestion = None
        if not compliant:
            suggestion = _infer_suggestion(field)

        results.append(FieldComplianceResult(
            field_name=field,
            compliant=compliant,
            suggestion=suggestion,
            matched_term=matched_term,
        ))

    return results


def _to_term(raw: dict) -> GlossaryTerm:
    return GlossaryTerm(
        name=raw.get("name", ""),
        guid=raw.get("guid"),
        short_description=raw.get("shortDescription"),
        long_description=raw.get("longDescription"),
        status=raw.get("status"),
        examples=raw.get("examples", []),
    )
