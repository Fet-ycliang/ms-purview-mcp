"""
cache 模組 unit tests（純本地邏輯，不需外部 API）。
執行：uv run pytest tests/test_cache.py -v
"""
import pytest

from purview_mcp.cache import (
    CACHE_TYPES,
    CacheManager,
    CacheStats,
    get_cache_manager,
    make_key,
    reset_cache_manager,
)


@pytest.fixture(autouse=True)
def fresh_cache():
    """每個測試前重置 singleton，避免互相影響。"""
    reset_cache_manager()
    yield
    reset_cache_manager()


# ──────────────────────────────────────────
# CT-01: make_key — cache key 產生
# ──────────────────────────────────────────
class TestMakeKey:
    def test_simple_args(self):
        """不同參數產生不同 key"""
        assert make_key("a", 1) != make_key("a", 2)
        assert make_key("a", 1) == make_key("a", 1)

    def test_list_order_independent(self):
        """list 參數順序不影響 key（set 語意）"""
        k1 = make_key(["g1", "g2", "g3"])
        k2 = make_key(["g3", "g1", "g2"])
        assert k1 == k2, "list 內容相同，順序不同，但應產生相同 key"

    def test_long_list_uses_hash(self):
        """長 list 用 MD5 hash 壓縮，避免 key 過長"""
        long_list = [f"guid-{i}" for i in range(50)]
        key = make_key(long_list)
        assert "hash:" in key, "長 list 應使用 hash 壓縮"
        assert len(key) < 100, "壓縮後 key 不應過長"

    def test_kwargs_order_independent(self):
        """kwargs 順序不影響 key"""
        k1 = make_key("op", limit=10, entity_type="databricks_table")
        k2 = make_key("op", entity_type="databricks_table", limit=10)
        assert k1 == k2

    def test_empty_args(self):
        """完全無參數也能產生 key"""
        assert make_key() == ""


# ──────────────────────────────────────────
# CT-02: CacheManager — 命中與失效
# ──────────────────────────────────────────
class TestCacheManager:
    def test_get_miss_returns_none(self):
        mgr = CacheManager()
        assert mgr.get("entity", "nonexistent") is None
        assert mgr.stats.summary()["entity"]["misses"] == 1

    def test_set_then_get_hit(self):
        mgr = CacheManager()
        mgr.set("entity", "k1", {"name": "test"})
        assert mgr.get("entity", "k1") == {"name": "test"}
        summary = mgr.stats.summary()
        assert summary["entity"]["hits"] == 1
        assert summary["entity"]["misses"] == 0

    def test_invalidate_upsert_clears_related(self):
        """upsert_entity 應清 entity/lineage/search，保留 glossary"""
        mgr = CacheManager()
        mgr.set("entity", "e1", "entity-data")
        mgr.set("lineage", "l1", "lineage-data")
        mgr.set("search", "s1", "search-data")
        mgr.set("glossary", "g1", "glossary-data")

        cleared = mgr.invalidate("upsert_entity")

        assert set(cleared) == {"entity", "lineage", "search"}
        assert mgr.get("entity", "e1") is None
        assert mgr.get("lineage", "l1") is None
        assert mgr.get("search", "s1") is None
        assert mgr.get("glossary", "g1") == "glossary-data", "glossary 不應被清"

    def test_invalidate_add_lineage_only_clears_lineage(self):
        mgr = CacheManager()
        mgr.set("entity", "e1", "x")
        mgr.set("lineage", "l1", "y")

        cleared = mgr.invalidate("add_lineage")

        assert cleared == ["lineage"]
        assert mgr.get("entity", "e1") == "x"
        assert mgr.get("lineage", "l1") is None

    def test_invalidate_unknown_operation_noop(self):
        """未登記的 operation 不清任何 cache"""
        mgr = CacheManager()
        mgr.set("entity", "e1", "x")
        cleared = mgr.invalidate("unknown_op")
        assert cleared == []
        assert mgr.get("entity", "e1") == "x"

    def test_clear_specific_type(self):
        """clear('entity') 只清 entity cache"""
        mgr = CacheManager()
        mgr.set("entity", "e1", "x")
        mgr.set("lineage", "l1", "y")

        cleared = mgr.clear("entity")

        assert cleared == {"entity": 1}
        assert mgr.get("entity", "e1") is None
        assert mgr.get("lineage", "l1") == "y"

    def test_clear_all(self):
        mgr = CacheManager()
        for name in CACHE_TYPES:
            mgr.set(name, "k", "v")

        cleared = mgr.clear("all")

        assert set(cleared.keys()) == set(CACHE_TYPES)
        for name in CACHE_TYPES:
            assert mgr.size(name) == 0

    def test_clear_invalid_type_raises(self):
        mgr = CacheManager()
        with pytest.raises(ValueError, match="不支援的 cache_type"):
            mgr.clear("not_a_real_cache")

    def test_all_sizes(self):
        mgr = CacheManager()
        mgr.set("entity", "e1", "x")
        mgr.set("entity", "e2", "y")
        mgr.set("glossary", "g1", "z")

        sizes = mgr.all_sizes()

        assert sizes["entity"] == 2
        assert sizes["glossary"] == 1
        assert sizes["lineage"] == 0
        assert sizes["search"] == 0


# ──────────────────────────────────────────
# CT-03: CacheStats — 統計計算
# ──────────────────────────────────────────
class TestCacheStats:
    def test_hit_rate_zero_when_no_activity(self):
        stats = CacheStats()
        summary = stats.summary()
        assert summary["entity"]["hit_rate"] == 0.0
        assert summary["entity"]["hits"] == 0

    def test_hit_rate_calculation(self):
        stats = CacheStats()
        for _ in range(3):
            stats.record_hit("entity")
        stats.record_miss("entity")

        summary = stats.summary()
        assert summary["entity"]["hits"] == 3
        assert summary["entity"]["misses"] == 1
        assert summary["entity"]["hit_rate"] == 0.75


# ──────────────────────────────────────────
# CT-04: Singleton
# ──────────────────────────────────────────
class TestSingleton:
    def test_get_cache_manager_returns_same_instance(self):
        m1 = get_cache_manager()
        m2 = get_cache_manager()
        assert m1 is m2

    def test_reset_creates_fresh_instance(self):
        m1 = get_cache_manager()
        m1.set("entity", "k", "v")
        reset_cache_manager()
        m2 = get_cache_manager()
        assert m1 is not m2
        assert m2.get("entity", "k") is None
