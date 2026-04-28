"""
E2E 測試：直接呼叫 Purview API，驗證每個 skill 的連線與回傳格式。
需要 .env 設定好 AZURE_* 與 PURVIEW_ACCOUNT_NAME。
執行：uv run pytest tests/test_e2e.py -v
"""
import pytest
import asyncio
from purview_mcp.models import Settings
from purview_mcp.auth import get_token
from purview_mcp.client.purview import PurviewClient
from purview_mcp.models import LineageResult
from purview_mcp.skills import discovery, glossary, lineage, policy, uc_sync


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def client(settings: Settings) -> PurviewClient:
    return PurviewClient(settings)


# ──────────────────────────────────────────
# TC-01: 認證層 — Token 取得
# ──────────────────────────────────────────
class TestAuthentication:
    def test_get_token_returns_non_empty_string(self, settings: Settings):
        """TC-01: Service Principal 可以成功取得 Bearer Token"""
        token = get_token(settings)
        assert isinstance(token, str)
        assert len(token) > 50, "Token 長度異常，可能認證失敗"

    def test_token_is_jwt_format(self, settings: Settings):
        """TC-01b: Token 格式應為 JWT（三段 Base64 以 . 分隔）"""
        token = get_token(settings)
        parts = token.split(".")
        assert len(parts) == 3, f"Token 不是 JWT 格式: {token[:30]}..."


# ──────────────────────────────────────────
# TC-02: Purview 連線 — 基本 Health Check
# ──────────────────────────────────────────
class TestPurviewConnection:
    def test_purview_base_url_format(self, settings: Settings):
        """TC-02: Purview base URL 格式正確"""
        url = settings.purview_base_url
        assert url.startswith("https://")
        assert "purview.azure.com" in url

    @pytest.mark.asyncio
    async def test_search_returns_list(self, client: PurviewClient):
        """TC-02b: 對 Purview 發出搜尋請求，回傳值為 list（允許空清單）"""
        result = await client.search(keywords="*", limit=1)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_glossary_endpoint_reachable(self, client: PurviewClient):
        """TC-02c: Glossary endpoint 可連線"""
        result = await client.get_glossary(limit=1)
        assert isinstance(result, list)


# ──────────────────────────────────────────
# TC-03: Skill — Data Discovery
# ──────────────────────────────────────────
class TestDiscoverySkill:
    @pytest.mark.asyncio
    async def test_search_assets_returns_asset_list(self, settings: Settings):
        """TC-03: search_assets 回傳 AssetResult 清單"""
        results = await discovery.search_assets(settings, keywords="*", limit=5)
        assert isinstance(results, list)
        for r in results:
            assert r.name, "AssetResult.name 不應為空"
            assert r.entity_type, "AssetResult.entity_type 不應為空"

    @pytest.mark.asyncio
    async def test_search_with_entity_type_filter(self, settings: Settings):
        """TC-03b: entity_type filter 只回傳指定類型"""
        results = await discovery.search_assets(
            settings, keywords="*", limit=5, entity_type="databricks_table"
        )
        for r in results:
            assert r.entity_type == "databricks_table", (
                f"期望 databricks_table，實際為 {r.entity_type}"
            )

    @pytest.mark.asyncio
    async def test_search_limit_respected(self, settings: Settings):
        """TC-03c: 回傳筆數不超過 limit"""
        results = await discovery.search_assets(settings, keywords="*", limit=3)
        assert len(results) <= 3


# ──────────────────────────────────────────
# TC-04: Skill — Glossary
# ──────────────────────────────────────────
class TestGlossarySkill:
    @pytest.mark.asyncio
    async def test_list_terms_returns_list(self, settings: Settings):
        """TC-04: list_terms 回傳 GlossaryTerm 清單"""
        terms = await glossary.list_terms(settings)
        assert isinstance(terms, list)

    @pytest.mark.asyncio
    async def test_list_terms_with_keyword_filters(self, settings: Settings):
        """TC-04b: 關鍵字過濾有效"""
        all_terms = await glossary.list_terms(settings)
        if not all_terms:
            pytest.skip("詞彙表為空，跳過此測試")
        keyword = all_terms[0].name[:3]
        filtered = await glossary.list_terms(settings, keyword=keyword)
        assert len(filtered) <= len(all_terms)
        for t in filtered:
            assert keyword.lower() in t.name.lower() or keyword.lower() in (t.short_description or "").lower()

    @pytest.mark.asyncio
    async def test_check_compliance_returns_dict(self, settings: Settings):
        """TC-04c: check_compliance 回傳 dict，key 為欄位名稱"""
        fields = ["customer_id", "order_date", "random_xyz_field_123"]
        result = await glossary.check_compliance(settings, fields)
        assert isinstance(result, dict)
        for field in fields:
            assert field in result


# ──────────────────────────────────────────
# TC-05: Skill — Policy / PII Labels
# ──────────────────────────────────────────
class TestPolicySkill:
    """Policy 測試會自動從 Discovery 抓一個實際存在的 databricks_table 來測。"""

    @pytest.fixture(scope="class")
    async def sample_qn(self, settings: Settings) -> str:
        """自動從 Purview 抓一個 databricks_table 的 qualified_name。"""
        results = await discovery.search_assets(
            settings, keywords="*", limit=1, entity_type="databricks_table"
        )
        if not results:
            pytest.skip("Purview 中沒有 databricks_table 資產，跳過 Policy 測試")
        return results[0].qualified_name

    @pytest.mark.asyncio
    async def test_get_labels_for_known_asset(self, settings: Settings, sample_qn: str):
        """TC-05: 對實際存在的 databricks_table 查詢敏感標籤"""
        labels = await policy.get_sensitivity_labels(settings, sample_qn)
        assert isinstance(labels, list)

    @pytest.mark.asyncio
    async def test_has_pii_returns_bool(self, settings: Settings, sample_qn: str):
        """TC-05b: has_pii 回傳 bool 型別"""
        result = await policy.has_pii(settings, sample_qn)
        assert isinstance(result, bool)


# ──────────────────────────────────────────
# TC-06: Models 驗證
# ──────────────────────────────────────────
class TestModels:
    def test_settings_purview_url(self):
        """TC-06: Settings.purview_base_url property 正確組合 URL"""
        from purview_mcp.models import Settings as S
        from unittest.mock import patch
        with patch.dict("os.environ", {
            "AZURE_TENANT_ID": "t", "AZURE_CLIENT_ID": "c",
            "AZURE_CLIENT_SECRET": "s", "PURVIEW_ACCOUNT_NAME": "myaccount",
            "DATABRICKS_HOST": "https://x.azuredatabricks.net",
        }):
            s = S()
            assert s.purview_base_url == "https://myaccount.purview.azure.com"

    def test_asset_result_defaults(self):
        """TC-06b: AssetResult 預設值正確"""
        from purview_mcp.models import AssetResult
        a = AssetResult(name="test", qualified_name="q", entity_type="t")
        assert a.labels == []
        assert a.description is None
        assert a.guid is None
        assert a.owner is None
        assert a.experts == []

    def test_uc_table_info_alias(self):
        """TC-06c: UCTableInfo 接受 'schema' alias"""
        from purview_mcp.models import UCTableInfo
        t = UCTableInfo(catalog="main", schema="cbss", table_name="orders")
        assert t.schema_name == "cbss"


# ──────────────────────────────────────────
# TC-07: Skill — Lineage
# ──────────────────────────────────────────
class TestLineageSkill:
    """Lineage 測試自動從 Discovery 抓一個實際資產的 qualified_name。"""

    @pytest.fixture(scope="class")
    async def sample_qn(self, settings: Settings) -> str:
        results = await discovery.search_assets(
            settings, keywords="*", limit=1, entity_type="databricks_table"
        )
        if not results:
            pytest.skip("Purview 中沒有 databricks_table 資產，跳過 Lineage 測試")
        return results[0].qualified_name

    @pytest.mark.asyncio
    async def test_get_lineage_returns_result(self, settings: Settings, sample_qn: str):
        """TC-07: get_lineage 回傳 LineageResult，upstream/downstream 為 list"""
        result = await lineage.get_lineage(settings, sample_qn)
        assert isinstance(result, LineageResult)
        assert isinstance(result.upstream, list)
        assert isinstance(result.downstream, list)

    @pytest.mark.asyncio
    async def test_get_lineage_input_direction(self, settings: Settings, sample_qn: str):
        """TC-07b: direction=INPUT 只回傳上游，downstream 為空"""
        result = await lineage.get_lineage(settings, sample_qn, direction="INPUT")
        assert isinstance(result.upstream, list)
        assert result.downstream == []

    @pytest.mark.asyncio
    async def test_get_lineage_output_direction(self, settings: Settings, sample_qn: str):
        """TC-07c: direction=OUTPUT 只回傳下游，upstream 為空"""
        result = await lineage.get_lineage(settings, sample_qn, direction="OUTPUT")
        assert isinstance(result.downstream, list)
        assert result.upstream == []


# ──────────────────────────────────────────
# TC-08: Skill — UC Sync (dry run only)
# ──────────────────────────────────────────
class TestUCSyncSkill:
    @pytest.mark.asyncio
    async def test_dry_run_returns_preview(self, settings: Settings):
        """TC-08: sync_uc_to_purview dry_run=True 回傳 count 與 entities 清單"""
        result = await uc_sync.sync_uc_to_purview(settings, dry_run=True)
        assert "dry_run" in result
        assert result["dry_run"] is True
        assert "count" in result
        assert isinstance(result["count"], int)

    @pytest.mark.asyncio
    async def test_dry_run_specific_catalog(self, settings: Settings):
        """TC-08b: 指定 catalog=prod_catalog 時 dry_run 仍正確運作"""
        result = await uc_sync.sync_uc_to_purview(
            settings, catalog="prod_catalog", dry_run=True
        )
        assert result.get("dry_run") is True

    @pytest.mark.asyncio
    async def test_dry_run_specific_schema(self, settings: Settings):
        """TC-08c: 指定 schema_name=pstage 時 dry_run 不報錯"""
        result = await uc_sync.sync_uc_to_purview(
            settings, catalog="prod_catalog", schema_name="pstage", dry_run=True
        )
        assert "dry_run" in result or "synced" in result
