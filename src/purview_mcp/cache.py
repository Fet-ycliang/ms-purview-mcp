"""
本地快取模組：針對 Purview API 熱點查詢提供 in-memory TTL 快取。

設計重點：
- 4 種獨立 cache（entity / lineage / glossary / search），每種有不同 TTL
- 寫操作（upsert_entity / add_lineage）會失效受影響的 cache
- 錯誤不快取（避免 403/404 反覆回傳失敗）
- 並發策略：不做 per-key lock。MCP 使用場景為單一 session 串行呼叫，
  同 key 並發機率極低；必要時再加
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Iterable

from cachetools import TTLCache

logger = logging.getLogger("purview_mcp.cache")

# TTL 設定（秒）
_TTL_GLOSSARY = 24 * 60 * 60  # 24h：企業詞彙極穩定
_TTL_ENTITY = 60 * 60         # 1h：table metadata 低頻變動
_TTL_LINEAGE = 30 * 60        # 30m：ETL 偶爾變動
_TTL_SEARCH = 5 * 60          # 5m：較頻繁變動

CACHE_TYPES = ("entity", "lineage", "glossary", "search")

# 寫操作對應要失效的 cache 名稱
_INVALIDATION_MAP: dict[str, tuple[str, ...]] = {
    "upsert_entity": ("entity", "lineage", "search"),
    "add_lineage": ("lineage",),
}


class CacheStats:
    """per-cache 命中統計，DEBUG 模式下記錄到 log。"""

    def __init__(self) -> None:
        self._hits: dict[str, int] = {name: 0 for name in CACHE_TYPES}
        self._misses: dict[str, int] = {name: 0 for name in CACHE_TYPES}

    def record_hit(self, cache_name: str) -> None:
        self._hits[cache_name] += 1
        logger.debug("cache HIT  | %s | total=%d", cache_name, self._hits[cache_name])

    def record_miss(self, cache_name: str) -> None:
        self._misses[cache_name] += 1
        logger.debug("cache MISS | %s | total=%d", cache_name, self._misses[cache_name])

    def summary(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name in CACHE_TYPES:
            hits = self._hits[name]
            misses = self._misses[name]
            total = hits + misses
            out[name] = {
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hits / total, 3) if total else 0.0,
            }
        return out


class CacheManager:
    """
    管理 4 種 TTLCache 的命中、失效與清除。

    用法：
        mgr = get_cache_manager()
        cached = mgr.get("entity", key)
        if cached is None:
            cached = await fetch()
            mgr.set("entity", key, cached)
    """

    def __init__(self) -> None:
        self._caches: dict[str, TTLCache] = {
            "glossary": TTLCache(maxsize=50, ttl=_TTL_GLOSSARY),
            "entity": TTLCache(maxsize=500, ttl=_TTL_ENTITY),
            "lineage": TTLCache(maxsize=200, ttl=_TTL_LINEAGE),
            "search": TTLCache(maxsize=300, ttl=_TTL_SEARCH),
        }
        self.stats = CacheStats()

    def get(self, cache_name: str, key: str) -> Any | None:
        """命中回傳值，未命中回傳 None。"""
        cache = self._caches[cache_name]
        if key in cache:
            self.stats.record_hit(cache_name)
            return cache[key]
        self.stats.record_miss(cache_name)
        return None

    def set(self, cache_name: str, key: str, value: Any) -> None:
        self._caches[cache_name][key] = value

    def invalidate(self, operation: str) -> list[str]:
        """寫操作後清空相關 cache。回傳被清的 cache 名稱。"""
        affected = _INVALIDATION_MAP.get(operation, ())
        for name in affected:
            self._caches[name].clear()
        if affected:
            logger.debug("cache invalidate | op=%s | cleared=%s", operation, affected)
        return list(affected)

    def clear(self, cache_type: str = "all") -> dict[str, int]:
        """
        清空指定 cache 或全部。回傳每個 cache 被清空前的項目數。

        cache_type: "all" | "entity" | "lineage" | "glossary" | "search"
        """
        cleared: dict[str, int] = {}
        if cache_type == "all":
            targets = CACHE_TYPES
        elif cache_type in CACHE_TYPES:
            targets = (cache_type,)
        else:
            raise ValueError(
                f"不支援的 cache_type: {cache_type!r}。"
                f"可用值：'all' 或 {list(CACHE_TYPES)}"
            )
        for name in targets:
            cleared[name] = len(self._caches[name])
            self._caches[name].clear()
        return cleared

    def size(self, cache_name: str) -> int:
        return len(self._caches[cache_name])

    def all_sizes(self) -> dict[str, int]:
        return {name: len(c) for name, c in self._caches.items()}

    def reset(self) -> None:
        """測試用：清全部 cache 與 stats。"""
        for c in self._caches.values():
            c.clear()
        self.stats = CacheStats()


def make_key(*args: Any, **kwargs: Any) -> str:
    """
    將函式參數組合成 cache key。

    - 一般純值：repr + join
    - list/tuple：先 sorted() 再 MD5（順序無關 + 避免 key 過長）
    - dict kwargs：先依 key 排序確保穩定
    """
    parts: list[str] = []
    for a in args:
        parts.append(_encode(a))
    for k in sorted(kwargs.keys()):
        parts.append(f"{k}={_encode(kwargs[k])}")
    return "|".join(parts)


def _encode(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        joined = ",".join(sorted(str(v) for v in value))
        # 長 list（例如 bulk GUID）用 hash 避免 key 過長
        if len(joined) > 200:
            return f"hash:{hashlib.md5(joined.encode()).hexdigest()}"
        return f"[{joined}]"
    return repr(value)


# ──────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────

_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """取得全域唯一的 CacheManager。"""
    global _manager
    if _manager is None:
        _manager = CacheManager()
    return _manager


def reset_cache_manager() -> None:
    """測試用：重置 singleton。"""
    global _manager
    _manager = None
