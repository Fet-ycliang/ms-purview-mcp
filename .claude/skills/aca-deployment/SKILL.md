---
name: aca-deployment
description: |
  purview-mcp 的 ACA 部署指引。用於設定環境變數、azd 部署到 Azure Container Apps、
  Entra ID app 註冊、APIM 界接，以及部署後驗證。
  觸發詞："azd up", "Azure 部署", "ACA 部署", "deploy purview-mcp", "APIM 設定", "Entra 註冊"。
---

# purview-mcp ACA 部署指引

此技能專門處理 `ms-purview-mcp` 的 ACA 部署步驟。

## 架構

```
Claude Code / Databricks
        ↓ HTTPS + OAuth
    APIM（現有，API path: /purview-mcp）
        ↓
    ACA ms-purview-mcp-ca（external ingress, port 8080）
        ↓
  Purview REST API + Databricks Unity Catalog
```

## 主要檔案

| 檔案 | 用途 |
|------|------|
| `Dockerfile` | Python/uv 多階段構建 |
| `azure.yaml` | azd 入口設定（host: containerapp）|
| `infra/main.bicep` | Bicep 主檔（resourceGroup scope）|
| `infra/resources.bicep` | Container App + Managed Identity 定義 |
| `infra/main.parameters.json` | 部署參數（含環境變數映射）|
| `infra/modules/mcp-api.bicep` | APIM API 定義（Phase 3）|
| `.github/workflows/deploy-purview-mcp-aca.yml` | CI/CD workflow |

## 環境變數清單

### ACA 環境變數（infra/resources.bicep 注入）

| 名稱 | 來源 | 說明 |
|------|------|------|
| `USE_HTTP` | 硬寫 `true` | 啟用 streamable-http transport |
| `PORT` | 硬寫 `8080` | 監聽 port |
| `PURVIEW_TENANT_ID` | param | Purview runtime tenant ID |
| `PURVIEW_CLIENT_ID` | param | Purview runtime client ID |
| `PURVIEW_CLIENT_SECRET` | secret | Purview runtime client secret |
| `PURVIEW_ACCOUNT_NAME` | param | Purview 帳號名稱（不含 .purview.azure.com）|
| `DATABRICKS_HOST` | param | `https://<workspace>.azuredatabricks.net` |
| `DATABRICKS_TOKEN` | secret | Databricks PAT token |
| `UC_DEFAULT_CATALOG` | param | 預設 Unity Catalog catalog 名稱 |
| `UC_CATALOGS` | param | azd 設定用逗號分隔字串，如 `prod,dev`；部署時會轉成 JSON 陣列 |
| `AZURE_BOOTSTRAP_CONTAINER_IMAGE` | param | 初次 provision 用的 public image，預設 `mcr.microsoft.com/dotnet/samples:aspnetapp` |

### azd 環境變數（.azure/<env>/.env）

> 目前 `infra/main.parameters.json` 為了相容既有 azd 環境，仍從 `AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET` 讀取 Purview runtime 認證，但注入 ACA 後會轉成 `PURVIEW_*` container env。GitHub deploy 則建議改用 `AZURE_DEPLOY_*`。

```bash
AZURE_ENV_NAME=purview-mcp-dev
AZURE_LOCATION=eastasia
AZURE_RESOURCE_GROUP_NAME=rg-xxx
AZURE_RESOURCE_NAME_STEM=ms-purview-mcp
AZURE_CONTAINER_REGISTRY_NAME=fetimageacr
AZURE_CONTAINER_REGISTRY_ENDPOINT=fetimageacr.azurecr.io
AZURE_CAE_NAME=cae-fet-outlook-email-env
AZURE_TENANT_ID=...         # 相容舊版，實際部署到 ACA 時會映射為 PURVIEW_TENANT_ID
AZURE_CLIENT_ID=...         # 相容舊版，實際部署到 ACA 時會映射為 PURVIEW_CLIENT_ID
AZURE_CLIENT_SECRET=...     # 相容舊版，實際部署到 ACA 時會映射為 PURVIEW_CLIENT_SECRET
PURVIEW_ACCOUNT_NAME=...
DATABRICKS_HOST=...
DATABRICKS_TOKEN=...
UC_DEFAULT_CATALOG=prod_catalog
UC_CATALOGS=prod_catalog,dev_catalog
AZURE_BOOTSTRAP_CONTAINER_IMAGE=mcr.microsoft.com/dotnet/samples:aspnetapp
```

## Phase 1 + 2 部署流程

```bash
# 1. 登入
azd auth login

# 2. 建立環境
azd env new purview-mcp-dev
# 設定必要環境變數（見上方清單）

# 3. 部署 infrastructure + container app
azd up
# 或分開執行：
azd provision    # 只建 infra（先以 bootstrap image 建 ACA）
azd deploy       # 本機 / 手動部署 image

# 4. 驗證（ACA direct）
curl -X POST https://<aca-fqdn>/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# 預期：10 個工具（search_data_assets, get_data_lineage, ...）
```

## Phase 3 APIM 界接

### 事前確認（必做，避免影響 outlook-email）

```bash
# 讀取現有 APIM 所有 APIs
az apim api list --resource-group <rg> --service-name <apim> -o table

# 確認現有 Named Values（避免命名衝突）
az apim nv list --resource-group <rg> --service-name <apim> -o table
```

### Entra ID App 註冊（手動）

1. 在 Entra ID 建立「purview-mcp API」app registration
   - Expose API → Add scope：`mcp.access`、`user_impersonation`
   - App Role：`access_as_application`
   - 記錄：`tenant_id`, `client_id`, `app_id_uri`

2. Claude 公共用戶端（可重用 outlook-email 的）
   - 確認 redirect_uri 含 `http://localhost`

### azd APIM 部署

```bash
azd env set AZURE_APIM_NAME <apim-name>
azd env set MCP_APIM_RESOURCE_TENANT_ID <tenant>
azd env set MCP_APIM_RESOURCE_CLIENT_ID <client-id>
azd env set MCP_CLAUDE_CLIENT_ID <claude-client-id>
azd deploy
```

### APIM expose 建議

建議只 expose 一組 Purview MCP API：

- `GET /purview-mcp/mcp`
- `POST /purview-mcp/mcp`
- `GET /purview-mcp/.well-known/oauth-protected-resource`

兩條流量共用同一組 APIM policy：

1. Databricks remote MCP：application token，要求 `access_as_application`
2. Claude Code browser flow：delegated token，要求 `mcp.access`（相容 `user_impersonation`）

目前 repo 內的 `purview-mcp-api.policy.xml` 已包含：

- caller JWT 驗證
- delegated / application token 分流
- `McpAllowedCallerAppIdsCsv` allowlist
- APIM managed identity 對 backend 重新取 token

若最終要把 APIM 作為唯一入口，ACA 需要再收斂成 internal/private ingress，或至少補上額外網路限制，否則仍可能繞過 APIM 直打 ACA FQDN。

## CI/CD（GitHub Actions）

Workflow 路徑：`.github/workflows/deploy-purview-mcp-aca.yml`

參考 AuroraOps 的 ACR / ACA 自動上版模式：

- `develop` push：用 `az acr build` 建置並推送 image 到 ACR，但**不自動 rollout ACA**
- `main` push：同樣先建 image，再自動 `az containerapp update` rollout `ms-purview-mcp-ca`
- 這支 workflow 現在是 **純 deploy pipeline**，不在 build 前執行 unit tests；unit tests 改成 **local commit 前** 先跑
- Azure 登入採多模式 fallback：
  - `AZURE_CREDENTIALS` 存在時，優先走 AuroraOps 風格的 Azure CLI login
  - `AZURE_DEPLOY_CLIENT_SECRET`（或 legacy `AZURE_CLIENT_SECRET`）存在時，workflow 走 service principal secret login
  - deploy secret 不存在時，workflow 才走 GitHub OIDC
- 目前 deploy target 已比照 AuroraOps 固定在 workflow env，不再依賴 GitHub Variables
- GitHub deploy workflow 只做 build / push / rollout；`PURVIEW_*`、`DATABRICKS_*` 這些 runtime env 會在 `azd provision` 時寫進 ACA，不需要每次 deploy 都再提供一次
- `main` rollout 使用同次 build 產出的日期版 image tag，並等待：
  - `latestRevisionName == latestReadyRevisionName`
  - ACA 目前 container image 已切到本次部署 image
- 建議在本機安裝 Git pre-commit hook：共用腳本放在 `scripts/pre-commit`，複製到 `.git/hooks/pre-commit` 後，可在 **local commit 前** 自動執行 `python -m pytest tests/ -m "not e2e" -v --tb=short`

Image naming：

- ACR image name：`ms-purview-mcp`
- main 穩定 tag：`latest`
- main 日期 tag：`YYYYMMDD-sha7`
- develop 穩定 tag：`develop`
- develop 日期 tag：`develop-YYYYMMDD-sha7`

預設設定：

| 名稱 | 預設值 |
|------|--------|
| `ACA_NAME` | `ms-purview-mcp-ca` |
| `ACA_CONTAINER_NAME` | `main` |
| `IMAGE_NAME` | `ms-purview-mcp` |

## 已知陷阱

- 先把 workflow 邊界講清楚：**develop = build / push image，main = build / push + rollout ACA**。這支 workflow 是 deploy pipeline，不是純 CI；unit tests 應在 **local commit 前** 先完成
- `AZURE_CREDENTIALS` 主路徑改用 **Azure CLI login** 後，比直接走 `azure/login` 更穩；主要不是功能差異，而是可避開 deploy 主流程持續出現的 Node 20 action 警告
- `az containerapp update` 若遇到 Azure Resource Manager 暫時性 503，Azure CLI 可能把 HTML 錯誤頁誤判成 JSON，最後噴出 `JSONDecodeError`；這通常不是憑證錯或 image 錯，應優先用 retry 吸收
- deploy workflow 已改成 **直接 bypass unit tests**，避免 build 太晚才被 runner / 內網環境卡住；unit tests 請在 **local commit 前** 執行，例如：`python -m pytest tests/ -m "not e2e" -v --tb=short`
- GitHub Actions 目前讀的是 **Repository-level** Variables / Secrets；若 GitHub UI 要求先建立 `Environment Name`，代表你進到 Environment 層級，不是本 workflow 使用的位置
- 目前 GitHub deploy workflow 只需要 **`AZURE_CREDENTIALS` 這一個 secret**；`PURVIEW_ACCOUNT_NAME`、`DATABRICKS_HOST`、`DATABRICKS_TOKEN` 這些 runtime 設定不應再放到 GitHub deploy workflow
- 若 GitHub Actions 在 `azure/login` 報 `AADSTS70025`，代表目前走的是 OIDC，但 Entra App 尚未設定 GitHub federated credential。可先保留 `AZURE_DEPLOY_CLIENT_SECRET` 讓 workflow 走 service principal secret login，或補上 branch 對應的 federated credential
- cross-tenant 時請把 **部署身分** 與 **Purview runtime 身分** 分離：GitHub deploy 用 `AZURE_DEPLOY_*`，app / `.env` 用 `PURVIEW_*`
- `azd env new` / `azd provision` 必須在專案根目錄執行；否則會出現 `no project exists; to create a new project, run azd init`
- `azd env set` 一律用 `azd env set KEY VALUE`；不要混用 `KEY=VALUE`
- `AZURE_ENV_NAME` 只代表 azd 環境，`AZURE_CAE_NAME` 才是既有 ACA Environment 名稱
- `AZURE_LOCATION` 應使用 `eastus2` 這類 CLI 代碼，不要填顯示名稱 `East US 2`
- `AZURE_SUBSCRIPTION_ID` 建議填真正的 subscription GUID。secret login 雖可用 `az account set --subscription` 接受名稱，但 OIDC 路徑仍應使用 GUID
- `UC_CATALOGS` 在 azd env 與 `.env` 都用逗號分隔字串，例如 `prod_catalog,dev_catalog`；Bicep 內再轉成 JSON 陣列字串
- `azd provision` 是實際部署，不是 dry-run；初次建立 ACA 時要先用 `AZURE_BOOTSTRAP_CONTAINER_IMAGE`，避免 ACR 尚未有應用 image 導致 revision 建立失敗
- `USE_HTTP=true` 必須在容器環境變數中設定，否則 server 會跑 stdio mode 然後立即退出
- ACA `ingress.targetPort` 必須與 `PORT` 環境變數一致（8080）
- GitHub workflow 目前已固定使用 `fetimageacr.azurecr.io`；只有 `azd` 或特殊 registry endpoint 情境才需要另外設定 `AZURE_CONTAINER_REGISTRY_ENDPOINT`
- GitHub Actions runner 已逐步從 Node 20 遷移到 Node 24；`AZURE_CREDENTIALS` 主路徑已改用 Azure CLI login，避免 `azure/login` 的 Node 20 警告干擾主要 deploy 流程；fallback / OIDC 路徑仍保留 `azure/login@v2`
- GitHub Actions 若直接用 `uv run` 執行測試，會依 `uv.lock` 中的來源抓套件；當 lock 內是公司 Nexus URL 時，GitHub runner 會解析失敗。CI 應改成 `uv export --frozen` 後，用 `pip --isolated -i https://pypi.org/simple` 安裝測試依賴
- GitHub Actions runner 無法直接打公司內網 Databricks；**unit tests 不應依賴 Databricks 連線**，必須改用 mock / fake data 驗證邏輯
- `tests/test_e2e.py` 屬於真實整合測試，依賴外部 Purview / Databricks / Entra 環境；e2e 請改在本機或手動流程執行
- 由於 deploy workflow 已 bypass 測試，`tests/**` 也不再列入這支 workflow 的觸發條件；test-only 變更是否正確，應在 **local commit 前** 先驗證
- `az containerapp update` 偶發會遇到 Azure Resource Manager 503，且 Azure CLI 會把 HTML 錯誤頁誤當 JSON 解析而爆 `JSONDecodeError`；workflow 應補 retry 吸收這種暫時性錯誤
- `.dockerignore` 必須保留 `uv.lock` 進 build context，同時排除 `.azure` 避免 azd secrets 被送進 ACR build
- ACR remote build 無法存取公司內網套件 proxy 時，Docker build 要改走 public PyPI；不要直接把本機/公司 proxy 設定硬改成對外版本
- APIM API path `/purview-mcp` 不能與 outlook-email 的 `/` 衝突，部署前先確認
- Named Values 命名加 `PurviewMcp` 前綴，避免與 outlook-email 的 `Mcp*` 衝突
- 已曝光在對話或終端的 `AZURE_CLIENT_SECRET` / `DATABRICKS_TOKEN` 等憑證，應立即輪替
