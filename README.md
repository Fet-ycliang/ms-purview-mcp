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

- `develop` push：建置 `ms-purview-mcp` image，推送 `develop` 與 `develop-YYYYMMDD-sha7`
- `main` push：建置 `ms-purview-mcp` image，推送 `latest` 與 `YYYYMMDD-sha7`，再自動 rollout `ms-purview-mcp-ca`
- rollout 完成條件：`latestRevisionName` 與 `latestReadyRevisionName` 一致，且 ACA 目前 image 已切到本次日期版 tag

Workflow：`.github/workflows/deploy-purview-mcp-aca.yml`

#### GitHub Repository Variables

| 名稱 | 建議值 |
|------|--------|
| `AZURE_SUBSCRIPTION_ID` | 你的 Azure Subscription GUID，建議不要填 subscription display name |
| `AZURE_RESOURCE_GROUP_NAME` | `apim-app-bst-rg` |
| `AZURE_CONTAINER_REGISTRY_NAME` | `fetimageacr` |

#### GitHub Repository Secrets

| 名稱 | 說明 |
|------|------|
| `AZURE_CREDENTIALS` | **選用**。AuroraOps 風格單一 JSON secret，內容可直接使用 `az ad sp create-for-rbac --json-auth` 輸出；若有設定，workflow 會優先使用這個登入 Azure |
| `AZURE_DEPLOY_CLIENT_ID` | **建議使用**。GitHub 部署專用的 Service Principal Client ID |
| `AZURE_DEPLOY_TENANT_ID` | **建議使用**。GitHub 部署專用 tenant ID |
| `AZURE_DEPLOY_CLIENT_SECRET` | **建議使用**。GitHub 部署專用 secret；若保留此 secret，workflow 會走 service principal secret login |

> 目前 GitHub **deploy workflow 不會再讀取** `PURVIEW_*` / `DATABRICKS_*`。這些是 **azd provision / ACA runtime / 本機 `.env`** 用的執行期設定，不是 rollout image 時要重新提供的 secrets。
>
> Azure 登入優先序目前是：`AZURE_CREDENTIALS` → `AZURE_DEPLOY_*` → legacy `AZURE_*` → OIDC。
>
> workflow 仍保留 `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_CLIENT_SECRET` 作為 **legacy fallback**，避免現有設定立刻失效。但要處理 cross-tenant，請改用 `AZURE_DEPLOY_*` 與 `PURVIEW_*` 分離。
>
> 目前 repo 已實際清掉多餘的 GitHub 設定；若你沿用標準命名，`AZURE_CONTAINER_REGISTRY_ENDPOINT`、`AZURE_CONTAINER_APP_NAME`、`ACA_CONTAINER_NAME` 也不必再額外建立。

#### `.env` / azd env / ACA runtime 對照

| 本機 `.env` / azd env | 用途 |
|-----------------------|------|
| `PURVIEW_TENANT_ID` | Purview runtime tenant |
| `PURVIEW_CLIENT_ID` | Purview runtime client |
| `PURVIEW_CLIENT_SECRET` | Purview runtime secret |
| `PURVIEW_ACCOUNT_NAME` | Purview account name |
| `DATABRICKS_HOST` | Databricks workspace URL |
| `DATABRICKS_TOKEN` | Databricks PAT |
| `UC_DEFAULT_CATALOG` | 預設 catalog |
| `UC_CATALOGS` | 多 catalog 清單，格式 `prod_catalog,dev_catalog` |

> 這些值在 **azd provision** 時會寫進 ACA container env；後續 GitHub Actions 做的是 **image rollout**，不會在每次 deploy 時重設一次。

#### Cross-tenant 建議切法

- **部署身分**：GitHub Actions 只用 `AZURE_DEPLOY_*`，這組必須能看到 Azure subscription / ACR / ACA
- **Purview 執行身分**：應用程式只用 `PURVIEW_*`，這組必須在 Purview 所在 tenant 有權限
- **Databricks 執行身分**：若與 Purview 不同 tenant，繼續用既有 `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` / `DATABRICKS_TENANT_ID`

#### 部署踩坑與注意事項

- 目前 workflow 讀的是 **Repository-level** Variables / Secrets；如果 GitHub 頁面要求先取 `Environment Name`，代表你進到 Environment 層級，不是這次要設定的位置
- GitHub Actions 的 Azure 登入現在採 **多模式 fallback**：`AZURE_CREDENTIALS` 優先，其次 `AZURE_DEPLOY_*` / legacy `AZURE_*` 的 service principal secret login，最後才是 OIDC
- 若 workflow 在 `azure/login` 報 `AADSTS70025`，代表目前走的是 OIDC，但 Entra App 尚未設定 GitHub federated credential。處理方式二選一：保留 `AZURE_DEPLOY_CLIENT_SECRET` 讓 workflow 走 secret login，或在 Entra App 補上對應 branch 的 federated credential
- 若你要處理 cross-tenant，**不要**再把部署 SP 和 Purview runtime SP 共用同一組 `AZURE_*` GitHub secrets。請改成 `AZURE_DEPLOY_*` 與 `PURVIEW_*` 分離
- GitHub deploy workflow 現在只需要 **3 個 repo variables**（`AZURE_SUBSCRIPTION_ID`、`AZURE_RESOURCE_GROUP_NAME`、`AZURE_CONTAINER_REGISTRY_NAME`）與 **deploy secrets**；`PURVIEW_ACCOUNT_NAME`、`DATABRICKS_HOST`、`DATABRICKS_TOKEN` 不需要放在 GitHub
- `azd env new` / `azd provision` 必須在 repo 根目錄執行；如果不在 `azure.yaml` 所在目錄，會出現 `no project exists`
- `azd env set` 語法是 `azd env set KEY VALUE`，不要寫成 `KEY=VALUE`
- `AZURE_ENV_NAME` 是 azd 環境名；`AZURE_CAE_NAME` 是既有 Container Apps Environment 名稱，兩者不要混用
- `AZURE_LOCATION` 請用 `eastus2` 這種 Azure CLI 代碼，不要用 `East US 2`
- `AZURE_SUBSCRIPTION_ID` 建議填 Azure Subscription GUID。雖然 workflow 的 secret login 會嘗試用 `az account set --subscription` 接受名稱，但 OIDC 路徑仍應使用真正的 subscription GUID
- `UC_CATALOGS` 在 azd / `.env` 層請用逗號分隔字串，例如 `prod_catalog,dev_catalog`；不要直接塞 JSON 陣列
- `azd provision` 會真的建資源，不是單純驗證；初次建立 ACA 需先用 public bootstrap image，否則會卡在 ACR 尚未有 `latest`
- GitHub workflow 會自動把 `AZURE_CONTAINER_REGISTRY_NAME` 推成 `<acr>.azurecr.io`；只有你不是標準 ACR endpoint，或本機 `azd` 需要自訂 registry endpoint 時，才需要額外設定 `AZURE_CONTAINER_REGISTRY_ENDPOINT`
- GitHub Actions JavaScript actions 已逐步淘汰 Node 20；`actions/checkout` 與 `actions/setup-python` 應維持在 `v6`，避免新 runner 切到 Node 24 後出現 deprecation warning 或執行失敗
- GitHub Actions 的 `uv run` 會直接依 `uv.lock` 內的來源抓套件；若 lock 是由公司 Nexus 產生，runner 會因 DNS 無法解析而失敗。CI 測試應改用 `uv export --frozen` 匯出 requirements，再用 `pip --isolated -i https://pypi.org/simple` 安裝
- `tests/test_e2e.py` 需要真實 Purview / Databricks / Entra 憑證與外部服務可用性；GitHub workflow 預設只跑 `not e2e` 的 unit tests，e2e 請改在本機或手動流程執行
- workflow `paths` 記得包含 `tests/**`；否則你只修測試時，GitHub Actions 不會重跑，容易誤判「明明修好了但 CI 還停在舊錯誤」
- `.dockerignore` 必須保留 `uv.lock` 進 build context，但要排除 `.azure`，避免 secrets 被送進 remote build
- ACR remote build 無法解析公司內網 Nexus 時，Docker build 要走 public PyPI；不要反過來改壞本機 / 公司 proxy 的開發設定
- 若 secret 曾直接貼在對話、終端或 commit 歷史中，應視為外洩並立即輪替

---

## APIM expose 建議

建議維持 **單一路徑**：

- `GET /purview-mcp/mcp`
- `POST /purview-mcp/mcp`
- `GET /purview-mcp/.well-known/oauth-protected-resource`

兩條呼叫路徑共用同一組 API policy：

1. **Databricks remote MCP**：使用 application token，要求 app role `access_as_application`
2. **Claude Code browser flow**：使用 delegated token，要求 scope `mcp.access`（相容 legacy `user_impersonation`）

目前 repo 內的 APIM policy 已經照這個方向設計：

- 驗證 caller JWT
- 區分 delegated / application token
- 用 `McpAllowedCallerAppIdsCsv` 限制允許的 caller app
- APIM 再用 managed identity 對 ACA backend 取 token 並轉送

如果要讓 `Databricks / Claude Code -> APIM -> ACA` 成為**唯一正式入口**，下一步要把 ACA ingress 改成 private/internal，或加上額外 network / auth 限制。否則知道 ACA FQDN 的流量仍可繞過 APIM。

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
