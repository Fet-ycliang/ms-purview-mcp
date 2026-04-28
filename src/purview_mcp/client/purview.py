from __future__ import annotations

from typing import Any
import httpx

from ..auth import get_token
from ..models import Settings


class PurviewClient:
    """Purview REST API 封裝層，所有 HTTP 呼叫集中於此。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.purview_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_token(self._settings)}",
            "Content-Type": "application/json",
        }

    async def search(
        self,
        keywords: str,
        limit: int = 10,
        entity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/datamap/api/search/query"
        body: dict[str, Any] = {
            "keywords": keywords,
            "limit": limit,
        }
        if entity_type:
            body["filter"] = {"and": [{"entityType": entity_type}]}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
            return data.get("value", [])

    async def get_entity(self, guid: str) -> dict[str, Any]:
        url = f"{self._base}/datamap/api/atlas/v2/entity/guid/{guid}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def get_entity_by_qualified_name(
        self, qualified_name: str, type_name: str = "databricks_table"
    ) -> dict[str, Any]:
        url = f"{self._base}/datamap/api/atlas/v2/entity/uniqueAttribute/type/{type_name}"
        params = {"attr:qualifiedName": qualified_name}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_lineage(
        self, guid: str, direction: str = "BOTH", depth: int = 3
    ) -> dict[str, Any]:
        url = f"{self._base}/datamap/api/atlas/v2/lineage/{guid}"
        params = {"direction": direction, "depth": depth}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_glossary(self, limit: int = 100) -> list[dict[str, Any]]:
        url = f"{self._base}/datamap/api/atlas/v2/glossary"
        params = {"limit": limit}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return [data]

    async def get_glossary_terms(
        self, glossary_guid: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        url = f"{self._base}/datamap/api/atlas/v2/glossary/{glossary_guid}/terms"
        params = {"limit": limit}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()

    async def upsert_entity(self, entity_payload: dict[str, Any]) -> dict[str, Any]:
        """建立或更新 Purview entity（用於 UC 同步）。"""
        url = f"{self._base}/datamap/api/atlas/v2/entity/bulk"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=self._headers(), json=entity_payload)
            resp.raise_for_status()
            return resp.json()

    async def add_lineage(self, lineage_payload: dict[str, Any]) -> dict[str, Any]:
        """新增 lineage 關係。"""
        url = f"{self._base}/datamap/api/atlas/v2/relationship"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers(), json=lineage_payload)
            resp.raise_for_status()
            return resp.json()
