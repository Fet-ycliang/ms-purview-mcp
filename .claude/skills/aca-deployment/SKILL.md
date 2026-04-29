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
    ACA ca-purview-mcp（external ingress, port 8080）
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
| `AZURE_TENANT_ID` | param | Entra tenant ID |
| `AZURE_CLIENT_ID` | param | Service Principal client ID |
| `AZURE_CLIENT_SECRET` | secret | SP client secret |
| `PURVIEW_ACCOUNT_NAME` | param | Purview 帳號名稱（不含 .purview.azure.com）|
| `DATABRICKS_HOST` | param | `https://<workspace>.azuredatabricks.net` |
| `DATABRICKS_TOKEN` | secret | Databricks PAT token |
| `UC_DEFAULT_CATALOG` | param | 預設 Unity Catalog catalog 名稱 |
| `UC_CATALOGS` | param | JSON 陣列，如 `["prod","dev"]` |

### azd 環境變數（.azure/<env>/.env）

```bash
AZURE_ENV_NAME=purview-mcp-dev
AZURE_LOCATION=eastasia
AZURE_RESOURCE_GROUP_NAME=rg-xxx
AZURE_RESOURCE_NAME_STEM=purview-mcp
AZURE_CONTAINER_REGISTRY_NAME=fetimageacr
AZURE_CAE_NAME=cae-fet-outlook-email-env
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
PURVIEW_ACCOUNT_NAME=...
DATABRICKS_HOST=...
DATABRICKS_TOKEN=...
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
azd provision    # 只建 infra
azd deploy       # 只部署 image

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

## CI/CD（GitHub Actions）

Workflow 路徑：`.github/workflows/deploy-purview-mcp-aca.yml`

觸發條件：push to `main`，paths：
- `Dockerfile`
- `src/purview_mcp/**`
- `pyproject.toml`

Image tag：台北時間戳記 `yyyyMMdd-HHmmss`
ACR 路徑：`fetimageacr.azurecr.io/fet-purview-mcp-ca:<tag>`

## 已知陷阱

- `USE_HTTP=true` 必須在容器環境變數中設定，否則 server 會跑 stdio mode 然後立即退出
- ACA `ingress.targetPort` 必須與 `PORT` 環境變數一致（8080）
- APIM API path `/purview-mcp` 不能與 outlook-email 的 `/` 衝突，部署前先確認
- Named Values 命名加 `PurviewMcp` 前綴，避免與 outlook-email 的 `Mcp*` 衝突
