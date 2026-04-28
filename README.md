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
