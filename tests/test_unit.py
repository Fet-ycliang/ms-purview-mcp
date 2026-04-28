"""
Unit tests：使用 mock 取代真實 API，可在無憑證環境執行。
執行：uv run pytest tests/test_unit.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from purview_mcp.cache import reset_cache_manager
from purview_mcp.client.purview import reset_purview_client
from purview_mcp.models import Settings, UCColumnInfo, UCTableInfo
from purview_mcp.skills import lineage, policy, uc_sync
from purview_mcp.skills.uc_sync import _uc_table_to_atlas_entity


@pytest.fixture(autouse=True)
def _reset_singletons():
    """每個 test 前重置 cache 與 client singleton，避免交互污染。"""
    reset_cache_manager()
    reset_purview_client()
    yield
    reset_cache_manager()
    reset_purview_client()


@pytest.fixture
def settings():
    return Settings(
        azure_tenant_id="t",
        azure_client_id="c",
        azure_client_secret="s",
        purview_account_name="myaccount",
        databricks_host="https://x.azuredatabricks.net",
    )


# ──────────────────────────────────────────
# UT-01: Lineage Skill
# ──────────────────────────────────────────
class TestLineageUnit:
    @pytest.mark.asyncio
    async def test_upstream_downstream_parsed(self, settings):
        """UT-01: 正確解析上下游血緣關係"""
        mock_entity = {"entity": {"guid": "guid-base"}}
        mock_lineage = {
            "relations": [
                {"fromEntityId": "guid-up", "toEntityId": "guid-base"},
                {"fromEntityId": "guid-base", "toEntityId": "guid-down"},
            ],
            "guidEntityMap": {
                "guid-up": {
                    "typeName": "databricks_table",
                    "attributes": {"name": "upstream_table", "qualifiedName": "qn-up"},
                },
                "guid-down": {
                    "typeName": "databricks_table",
                    "attributes": {"name": "downstream_table", "qualifiedName": "qn-down"},
                },
            },
        }
        with patch("purview_mcp.skills.lineage.get_purview_client") as MockClient:
            client = MockClient.return_value
            client.get_entity_by_qualified_name = AsyncMock(return_value=mock_entity)
            client.get_lineage = AsyncMock(return_value=mock_lineage)

            result = await lineage.get_lineage(settings, "qn-base")

        assert result.base_entity_guid == "guid-base"
        assert len(result.upstream) == 1
        assert result.upstream[0].name == "upstream_table"
        assert result.upstream[0].qualified_name == "qn-up"
        assert len(result.downstream) == 1
        assert result.downstream[0].name == "downstream_table"

    @pytest.mark.asyncio
    async def test_no_relations(self, settings):
        """UT-01b: 無血緣關係時回傳空清單"""
        with patch("purview_mcp.skills.lineage.get_purview_client") as MockClient:
            client = MockClient.return_value
            client.get_entity_by_qualified_name = AsyncMock(return_value={"entity": {"guid": "g1"}})
            client.get_lineage = AsyncMock(return_value={"relations": [], "guidEntityMap": {}})

            result = await lineage.get_lineage(settings, "qn")

        assert result.upstream == []
        assert result.downstream == []

    @pytest.mark.asyncio
    async def test_direction_both_forwarded(self, settings):
        """UT-01c: direction 參數正確傳遞給 client"""
        with patch("purview_mcp.skills.lineage.get_purview_client") as MockClient:
            client = MockClient.return_value
            client.get_entity_by_qualified_name = AsyncMock(return_value={"entity": {"guid": "g1"}})
            client.get_lineage = AsyncMock(return_value={"relations": [], "guidEntityMap": {}})

            await lineage.get_lineage(settings, "qn", direction="INPUT", depth=2)

        client.get_lineage.assert_called_once_with("g1", "INPUT", 2)


# ──────────────────────────────────────────
# UT-02: Policy Skill
# ──────────────────────────────────────────
class TestPolicyUnit:
    def test_to_label_pii_detected(self):
        """UT-02: _to_label 正確偵測 PII 關鍵字"""
        assert policy._to_label({"typeName": "PII_PersonalData"}).is_pii is True
        assert policy._to_label({"typeName": "sensitive_customer"}).is_pii is True
        assert policy._to_label({"typeName": "gdpr_compliance"}).is_pii is True

    def test_to_label_non_pii(self):
        """UT-02b: _to_label 非 PII 標籤正確辨識"""
        assert policy._to_label({"typeName": "PublicData"}).is_pii is False
        assert policy._to_label({"name": "internal_only"}).is_pii is False

    @pytest.mark.asyncio
    async def test_has_pii_true(self, settings):
        """UT-02c: 含 PII 標籤時 has_pii 回傳 True"""
        with patch("purview_mcp.skills.policy.get_purview_client") as MockClient:
            client = MockClient.return_value
            client.get_entity_by_qualified_name = AsyncMock(return_value={
                "entity": {"classifications": [{"typeName": "PII_SensitiveData"}]}
            })
            assert await policy.has_pii(settings, "qn") is True

    @pytest.mark.asyncio
    async def test_has_pii_false(self, settings):
        """UT-02d: 無 PII 標籤時 has_pii 回傳 False"""
        with patch("purview_mcp.skills.policy.get_purview_client") as MockClient:
            client = MockClient.return_value
            client.get_entity_by_qualified_name = AsyncMock(return_value={
                "entity": {"classifications": [{"typeName": "PublicData"}]}
            })
            assert await policy.has_pii(settings, "qn") is False

    @pytest.mark.asyncio
    async def test_empty_classifications(self, settings):
        """UT-02e: 無任何標籤時回傳空清單"""
        with patch("purview_mcp.skills.policy.get_purview_client") as MockClient:
            client = MockClient.return_value
            client.get_entity_by_qualified_name = AsyncMock(return_value={"entity": {}})
            labels = await policy.get_sensitivity_labels(settings, "qn")
            assert labels == []


# ──────────────────────────────────────────
# UT-03: UC Sync Skill
# ──────────────────────────────────────────
class TestUCSyncUnit:
    def test_atlas_entity_structure(self, settings):
        """UT-03: _uc_table_to_atlas_entity 輸出正確的 Atlas entity 結構"""
        table = UCTableInfo(
            catalog="prod_catalog",
            schema="pstage",
            table_name="ocs_customer",
            columns=[UCColumnInfo(name="cust_id", type_text="string")],
        )
        entity = _uc_table_to_atlas_entity(table, settings)

        assert entity["typeName"] == "databricks_table"
        attrs = entity["attributes"]
        assert attrs["name"] == "ocs_customer"
        assert "prod_catalog/pstage/ocs_customer" in attrs["qualifiedName"]
        assert len(attrs["columns"]) == 1
        assert attrs["columns"][0]["attributes"]["name"] == "cust_id"
        assert attrs["columns"][0]["attributes"]["dataType"] == "string"

    def test_atlas_entity_unknown_type(self, settings):
        """UT-03b: 欄位無 type_text 時 dataType 預設為 unknown"""
        table = UCTableInfo(
            catalog="prod_catalog",
            schema="pstage",
            table_name="t1",
            columns=[UCColumnInfo(name="col1")],
        )
        entity = _uc_table_to_atlas_entity(table, settings)
        assert entity["attributes"]["columns"][0]["attributes"]["dataType"] == "unknown"

    @pytest.mark.asyncio
    async def test_dry_run_no_upsert(self, settings):
        """UT-03c: dry_run=True 不呼叫 PurviewClient.upsert"""
        mock_tables = [
            UCTableInfo(catalog="prod_catalog", schema="pstage", table_name="t1"),
            UCTableInfo(catalog="prod_catalog", schema="pstage", table_name="t2"),
        ]
        with patch("purview_mcp.skills.uc_sync.list_uc_tables", new=AsyncMock(return_value=mock_tables)), \
             patch("purview_mcp.skills.uc_sync.get_purview_client") as MockPurview:

            result = await uc_sync.sync_uc_to_purview(settings, dry_run=True)

        assert result["dry_run"] is True
        assert result["count"] == 2
        MockPurview.return_value.upsert_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_catalog_returns_zero(self, settings):
        """UT-03d: 空 catalog 時回傳 synced=0"""
        with patch("purview_mcp.skills.uc_sync.list_uc_tables", new=AsyncMock(return_value=[])):
            result = await uc_sync.sync_uc_to_purview(settings)

        assert result["synced"] == 0
        assert result["tables"] == []

    @pytest.mark.asyncio
    async def test_real_sync_calls_upsert(self, settings):
        """UT-03e: dry_run=False 確實呼叫 upsert_entity"""
        mock_tables = [
            UCTableInfo(catalog="prod_catalog", schema="pstage", table_name="t1"),
        ]
        with patch("purview_mcp.skills.uc_sync.list_uc_tables", new=AsyncMock(return_value=mock_tables)), \
             patch("purview_mcp.skills.uc_sync.get_purview_client") as MockPurview:
            MockPurview.return_value.upsert_entity = AsyncMock(return_value={"status": "ok"})

            result = await uc_sync.sync_uc_to_purview(settings, dry_run=False)

        assert result["synced"] == 1
        MockPurview.return_value.upsert_entity.assert_called_once()
