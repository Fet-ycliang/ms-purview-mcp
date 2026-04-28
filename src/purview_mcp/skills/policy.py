from __future__ import annotations

from ..client.purview import PurviewClient
from ..models import SensitivityLabel, Settings

_PII_LABEL_KEYWORDS = {"pii", "personal", "sensitive", "confidential", "gdpr", "個人"}


async def get_sensitivity_labels(
    settings: Settings,
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> list[SensitivityLabel]:
    """取得資料集的敏感度標籤。"""
    client = PurviewClient(settings)

    entity_data = await client.get_entity_by_qualified_name(qualified_name, entity_type)
    entity = entity_data.get("entity", {})

    raw_labels: list[dict] = (
        entity.get("classifications", [])
        or entity.get("attributes", {}).get("labels", [])
    )

    return [_to_label(lbl) for lbl in raw_labels]


async def has_pii(
    settings: Settings,
    qualified_name: str,
    entity_type: str = "databricks_table",
) -> bool:
    """判斷資料集是否含有 PII 敏感標籤。"""
    labels = await get_sensitivity_labels(settings, qualified_name, entity_type)
    return any(label.is_pii for label in labels)


def _to_label(raw: dict) -> SensitivityLabel:
    name = raw.get("typeName") or raw.get("name", "")
    is_pii = any(kw in name.lower() for kw in _PII_LABEL_KEYWORDS)
    return SensitivityLabel(
        label_name=name,
        label_id=raw.get("entityGuid"),
        is_pii=is_pii,
    )
