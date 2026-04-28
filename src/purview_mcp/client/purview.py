from __future__ import annotations

from typing import Any
import httpx

from ..auth import get_token
from ..cache import get_cache_manager, make_key
from ..models import Settings


class PurviewClient:
    """Purview REST API 封裝層。

    設計：
    - 共享一個 httpx.AsyncClient（connection pool 重用）
    - 讀操作查 CacheManager；未命中才打 API，成功後寫入 cache
    - 寫操作（upsert / add_lineage）執行後呼叫 cache invalidation
    - 錯誤（httpx.HTTPStatusError 等）不寫 cache

    正常用法：透過 module-level `get_purview_client(settings)` 取得 singleton。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.purview_base_url
        self._http = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._cache = get_cache_manager()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_token(self._settings)}",
            "Content-Type": "application/json",
        }

    async def aclose(self) -> None:
        """關閉底層 HTTP client。應在 MCP server 結束時呼叫。"""
        await self._http.aclose()

    # ──────────────────────────────────────────
    # Read operations（帶 cache）
    # ──────────────────────────────────────────

    async def search(
        self,
        keywords: str,
        limit: int = 10,
        entity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        key = make_key("search", keywords, limit, entity_type)
        cached = self._cache.get("search", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/search/query"
        body: dict[str, Any] = {"keywords": keywords, "limit": limit}
        if entity_type:
            body["filter"] = {"and": [{"entityType": entity_type}]}

        resp = await self._http.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        data = resp.json().get("value", [])
        self._cache.set("search", key, data)
        return data

    async def get_entity(self, guid: str) -> dict[str, Any]:
        key = make_key("get_entity", guid)
        cached = self._cache.get("entity", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/atlas/v2/entity/guid/{guid}"
        resp = await self._http.get(url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        self._cache.set("entity", key, data)
        return data

    async def get_entity_by_qualified_name(
        self, qualified_name: str, type_name: str = "databricks_table"
    ) -> dict[str, Any]:
        key = make_key("get_entity_by_qn", qualified_name, type_name)
        cached = self._cache.get("entity", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/atlas/v2/entity/uniqueAttribute/type/{type_name}"
        params = {"attr:qualifiedName": qualified_name}
        resp = await self._http.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        self._cache.set("entity", key, data)
        return data

    async def get_lineage(
        self, guid: str, direction: str = "BOTH", depth: int = 3
    ) -> dict[str, Any]:
        key = make_key("get_lineage", guid, direction, depth)
        cached = self._cache.get("lineage", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/atlas/v2/lineage/{guid}"
        params = {"direction": direction, "depth": depth}
        resp = await self._http.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        self._cache.set("lineage", key, data)
        return data

    async def get_glossary(self, limit: int = 100) -> list[dict[str, Any]]:
        key = make_key("get_glossary", limit)
        cached = self._cache.get("glossary", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/atlas/v2/glossary"
        params = {"limit": limit}
        resp = await self._http.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        result = data if isinstance(data, list) else [data]
        self._cache.set("glossary", key, result)
        return result

    async def get_glossary_terms(
        self, glossary_guid: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        key = make_key("get_glossary_terms", glossary_guid, limit)
        cached = self._cache.get("glossary", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/atlas/v2/glossary/{glossary_guid}/terms"
        params = {"limit": limit}
        resp = await self._http.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        self._cache.set("glossary", key, data)
        return data

    async def get_entities_bulk(self, guids: list[str]) -> dict[str, Any]:
        """一次取回多個 entity（用於批量查欄位定義）。"""
        key = make_key("get_entities_bulk", guids)
        cached = self._cache.get("entity", key)
        if cached is not None:
            return cached

        url = f"{self._base}/datamap/api/atlas/v2/entity/bulk"
        params = [("guid", g) for g in guids]
        resp = await self._http.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        self._cache.set("entity", key, data)
        return data

    # ──────────────────────────────────────────
    # Write operations（會 invalidate 相關 cache）
    # ──────────────────────────────────────────

    async def upsert_entity(self, entity_payload: dict[str, Any]) -> dict[str, Any]:
        """建立或更新 Purview entity（用於 UC 同步）。"""
        url = f"{self._base}/datamap/api/atlas/v2/entity/bulk"
        resp = await self._http.post(url, headers=self._headers(), json=entity_payload, timeout=60)
        resp.raise_for_status()
        self._cache.invalidate("upsert_entity")
        return resp.json()

    async def add_lineage(self, lineage_payload: dict[str, Any]) -> dict[str, Any]:
        """新增 lineage 關係。"""
        url = f"{self._base}/datamap/api/atlas/v2/relationship"
        resp = await self._http.post(url, headers=self._headers(), json=lineage_payload)
        resp.raise_for_status()
        self._cache.invalidate("add_lineage")
        return resp.json()


# ──────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────

_instance: PurviewClient | None = None


def get_purview_client(settings: Settings) -> PurviewClient:
    """取得 process 內共用的 PurviewClient。

    所有 skill 都應使用這個 factory，避免每次新建 client 導致：
    - 重複 TCP/TLS handshake
    - 各自獨立的 cache 失效
    """
    global _instance
    if _instance is None:
        _instance = PurviewClient(settings)
    return _instance


def reset_purview_client() -> None:
    """測試用：重置 singleton。不會自動 aclose 舊 instance。"""
    global _instance
    _instance = None
