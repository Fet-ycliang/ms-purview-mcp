# Purview MCP Server

將 Microsoft Purview 四大功能封裝為 Claude Code MCP Tools，整合 Databricks Unity Catalog。

## 快速開始

### 1. 安裝依賴

```bash
uv sync
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入 Service Principal 與 Databricks 連線資訊
```

### 3. 掛載到 Claude Code

將以下設定加入 `~/.claude/settings.json`（或專案的 `.claude/settings.json`）：

```json
{
  "mcpServers": {
    "purview": {
      "command": "uv",
      "args": ["run", "python", "-m", "purview_mcp.server"],
      "cwd": "D:/azure_code/Purview"
    }
  }
}
```

### 4. 驗證 MCP Server（可選）

```bash
uv run mcp dev src/purview_mcp/server.py
```

瀏覽器開啟 MCP Inspector，可直接測試每個 tool。

---

## Azure 部署

### 初始化 Azure 資源

首次建立 ACA / Managed Identity / 相關 Azure 資源時，仍使用 `azd`：

```bash
azd auth login
azd env new purview-mcp-dev
azd provision
```

目前預設資源名稱：

| 類型 | 名稱 |
|------|------|
| Container App | `ms-purview-mcp-ca` |
| Managed Identity | `ms-purview-mcp-id` |

### GitHub Actions 自動上版

`main` 與 `develop` 分支採用 AuroraOps 同款的 ACR / ACA 流程：

- `develop` push：建置 `purview-mcp-app` image，推送 `develop` 與 `develop-YYYYMMDD-sha7`
- `main` push：建置 `purview-mcp-app` image，推送 `latest` 與 `YYYYMMDD-sha7`，再自動 rollout `ms-purview-mcp-ca`
- rollout 完成條件：`latestRevisionName` 與 `latestReadyRevisionName` 一致，且 ACA 目前 image 已切到本次日期版 tag

Workflow：`.github/workflows/deploy-purview-mcp-aca.yml`

#### GitHub Repository Variables

| 名稱 | 建議值 |
|------|--------|
| `AZURE_SUBSCRIPTION_ID` | 你的 Azure Subscription ID |
| `AZURE_RESOURCE_GROUP_NAME` | `apim-app-bst-rg` |
| `AZURE_CONTAINER_REGISTRY_NAME` | `fetimageacr` |
| `AZURE_CONTAINER_REGISTRY_ENDPOINT` | `fetimageacr.azurecr.io` |
| `AZURE_CONTAINER_APP_NAME` | `ms-purview-mcp-ca` |
| `ACA_CONTAINER_NAME` | `main` |
| `PURVIEW_ACCOUNT_NAME` | `dge-purview-prod` |
| `DATABRICKS_HOST` | 你的 Databricks workspace URL |

#### GitHub Repository Secrets

| 名稱 | 說明 |
|------|------|
| `AZURE_CLIENT_ID` | GitHub OIDC 對應的 Service Principal Client ID |
| `AZURE_TENANT_ID` | Azure Tenant ID |
| `AZURE_CLIENT_SECRET` | Service Principal secret |
| `DATABRICKS_TOKEN` | Databricks PAT |

#### `.env` 與 CI 變數對照

| 本機 `.env` | GitHub 設定 |
|-------------|-------------|
| `AZURE_TENANT_ID` | `AZURE_TENANT_ID` secret |
| `AZURE_CLIENT_ID` | `AZURE_CLIENT_ID` secret |
| `AZURE_CLIENT_SECRET` | `AZURE_CLIENT_SECRET` secret |
| `PURVIEW_ACCOUNT_NAME` | `PURVIEW_ACCOUNT_NAME` variable |
| `DATABRICKS_HOST` | `DATABRICKS_HOST` variable |
| `DATABRICKS_TOKEN` | `DATABRICKS_TOKEN` secret |
| `UC_DEFAULT_CATALOG` | 目前 workflow 未使用，可保留本機設定 |
| `UC_CATALOGS` | 目前 workflow 未使用；若未來要加，請用 `prod_catalog,dev_catalog` 格式 |

#### 部署踩坑與注意事項

- 目前 workflow 讀的是 **Repository-level** Variables / Secrets；如果 GitHub 頁面要求先取 `Environment Name`，代表你進到 Environment 層級，不是這次要設定的位置
- `azd env new` / `azd provision` 必須在 repo 根目錄執行；如果不在 `azure.yaml` 所在目錄，會出現 `no project exists`
- `azd env set` 語法是 `azd env set KEY VALUE`，不要寫成 `KEY=VALUE`
- `AZURE_ENV_NAME` 是 azd 環境名；`AZURE_CAE_NAME` 是既有 Container Apps Environment 名稱，兩者不要混用
- `AZURE_LOCATION` 請用 `eastus2` 這種 Azure CLI 代碼，不要用 `East US 2`
- `UC_CATALOGS` 在 azd / `.env` 層請用逗號分隔字串，例如 `prod_catalog,dev_catalog`；不要直接塞 JSON 陣列
- `azd provision` 會真的建資源，不是單純驗證；初次建立 ACA 需先用 public bootstrap image，否則會卡在 ACR 尚未有 `latest`
- 若走 `azd deploy` 或 workflow build，請明確提供 `AZURE_CONTAINER_REGISTRY_ENDPOINT`，否則 remote build 可能找不到 registry endpoint
- GitHub Actions JavaScript actions 已逐步淘汰 Node 20；`actions/checkout` 與 `actions/setup-python` 應維持在 `v6`，避免新 runner 切到 Node 24 後出現 deprecation warning 或執行失敗
- `.dockerignore` 必須保留 `uv.lock` 進 build context，但要排除 `.azure`，避免 secrets 被送進 remote build
- ACR remote build 無法解析公司內網 Nexus 時，Docker build 要走 public PyPI；不要反過來改壞本機 / 公司 proxy 的開發設定
- 若 secret 曾直接貼在對話、終端或 commit 歷史中，應視為外洩並立即輪替

---

## 可用 Tools

| Tool | 說明 |
|------|------|
| `search_data_assets` | 搜尋 Purview 資料資產，預設優先 Databricks 類型 |
| `get_data_lineage` | 追蹤資料血緣（上下游） |
| `list_glossary_terms` | 列出企業詞彙表，支援關鍵字過濾 |
| `check_field_compliance` | 檢查欄位名稱是否符合企業詞彙規範 |
| `check_pii_labels` | 查詢資料集的 PII / 敏感標籤 |
| `sync_unity_catalog` | 將 Databricks UC metadata 同步到 Purview |

## 使用範例（在 Claude Code 對話中）

```
搜尋 customer transaction 相關的 Databricks 資料表
→ 呼叫 search_data_assets(keywords="customer transaction")

查詢 cbss.orders 這張表的上下游血緣
→ 呼叫 get_data_lineage(qualified_name="<workspace>/main/cbss/orders")

先預覽再同步 UC 的 cbss schema 到 Purview
→ 呼叫 sync_unity_catalog(schema_name="cbss", dry_run=True)
→ 確認後呼叫 sync_unity_catalog(schema_name="cbss", dry_run=False)
```
