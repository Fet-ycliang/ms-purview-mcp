# 踩雷紀錄與注意事項

開發 Purview MCP Server 過程中遇到的 API 行為異常、SDK 陷阱與架構決策。

---

## Purview REST API

### 1. Token scope 用 `.net` 不是 `.com`

```python
# 正確（早期版本 Azure Purview）
_PURVIEW_SCOPE = "https://purview.azure.net/.default"

# 錯誤（新版 Microsoft Purview，若用了會 401）
# _PURVIEW_SCOPE = "https://purview.azure.com/.default"
```

**除錯方式**：token 失敗時先解碼 JWT（jwt.io）確認 `aud` 欄位，
再到 Azure Portal → Enterprise Applications → 查 Service Principal 的 `appRoleAssignments`，
確認 scope 對應的 App ID。

---

### 2. Search API 不索引欄位（column）entity

```python
# 永遠回傳 0 結果，Purview 根本不索引 column entity
search_data_assets(entity_type="databricks_table_column")

# 正確做法：走 Databricks UC SDK 直接掃描
# 見 find_tables_by_column() 實作
```

---

### 3. `get_entities_bulk` 回傳結構不一致

`/entity/bulk` 的 `entities` 欄位可能是 `list` 也可能是 `dict`，需要兩種處理：

```python
bulk_data = await client.get_entities_bulk(guids)
entities = bulk_data.get("entities", {})
if isinstance(entities, list):
    entities = {e["guid"]: e for e in entities}   # 正規化成 dict
```

---

### 4. Column entity 的 typeName 在不同情境不一致

| 情境 | typeName |
|------|----------|
| table `relationshipAttributes.columns` 裡看到的 ref | `databricks_column` |
| 獨立查詢欄位 entity（get_entity by guid） | `databricks_table_column` |
| UC Sync 寫入 Purview 時用 | `databricks_column` |

建立 entity 時統一用 `databricks_column`（Purview Atlas type registry 的命名），
查詢時兩種都可能出現。

---

### 5. Owner 是 AAD Object ID，不是 display name

```python
# contacts.Owner[].id 回傳的是 AAD User GUID
# 例如: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
owners = [c["id"] for c in contacts.get("Owner", []) if c.get("id")]
```

要解析成 display name 需要額外呼叫 Azure AD Graph API
（`GET /v1.0/users/{id}`），目前未實作，直接回傳 GUID。

---

### 6. Bulk Entity API 同一 URL 讀寫行為不同

```
# 讀（取多個 entity）
GET /datamap/api/atlas/v2/entity/bulk?guid=aaa&guid=bbb

# 寫（建立/更新 entity）
POST /datamap/api/atlas/v2/entity/bulk
Body: {"entities": [...]}
```

`upsert_entity` 寫入後要記得呼叫 `cache.invalidate("upsert_entity")`，
否則舊的 entity cache 不會清掉。

---

## Databricks UC SDK

### 7. `tables.list(schema_name="")` 會失敗

空字串不等於 None，SDK 會把 `""` 當真實 schema 名稱：

```python
# 錯誤：schema_name="" 會讓 SDK 報錯
db.tables.list(catalog_name="prod_catalog", schema_name="")

# 正確：先列出 schemas 再 iterate
schemas = [s.name for s in db.schemas.list(catalog_name=catalog) if s.name]
for schema in schemas:
    for table in db.tables.list(catalog_name=catalog, schema_name=schema):
        ...
```

---

### 8. `find_tables_by_column` 是全表掃，速度慢

因為 Purview 不索引欄位，`find_tables_by_column` 會用 UC SDK 掃整個 catalog。
大型 catalog 可能需要數十秒，建議傳入 `schema_name` 縮小範圍。

---

## 快取架構

### 9. Cache 必須是 module-level singleton

若把 cache 放在 `PurviewClient` instance，每次 `PurviewClient(settings)` 都會有空 cache：

```python
# 錯誤：每個 skill 新建 client = 每次 cache 都是空的
client = PurviewClient(settings)

# 正確：module-level singleton，所有 skill 共享同一個 client 和 cache
client = get_purview_client(settings)
```

---

### 10. `make_key` 的 list 參數必須 sorted + MD5

```python
# get_entities_bulk(["a","b"]) 和 get_entities_bulk(["b","a"]) 應命中同一個 cache
# 直接 repr(list) 會因順序不同產生不同 key
sorted_items = sorted(str(i) for i in arg)
key = "hash:" + md5(",".join(sorted_items).encode()).hexdigest()
```

---

## 單元測試

### 11. Mock 目標從 `PurviewClient` 改為 `get_purview_client`

重構成 singleton 後，patch 目標也要跟著改：

```python
# 舊（重構前，現在失效）
with patch("purview_mcp.skills.lineage.PurviewClient") as MockClient:

# 新（singleton factory pattern）
with patch("purview_mcp.skills.lineage.get_purview_client") as MockClient:
    client = MockClient.return_value
    client.some_method = AsyncMock(return_value=...)
```

---

### 12. Singleton 跨測試互污染

`_instance` 是 module-level global，測試間會共享舊 instance（含舊 cache）：

```python
@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_cache_manager()
    reset_purview_client()
    yield
    reset_cache_manager()
    reset_purview_client()
```

---

## 資料欄位格式

### 13. `lastAltered` 是 Unix **毫秒**，不是秒

```python
# 計算距今天數
days = (now_ms - last_altered_ms) / (1000 * 60 * 60 * 24)

# 錯誤（少除 1000，天數會差 1000 倍）
# days = (now_ms - last_altered_ms) / (60 * 60 * 24)
```
