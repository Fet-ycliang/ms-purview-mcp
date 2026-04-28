---
name: project-guidelines
description: |
  AuroraOps 專案規範：繁體中文語言要求、git 工作流程、ADO 工作項目規則、Python 編碼標準。
  Use when: writing Python code, adding comments, git commits, ADO task/PBI descriptions, documentation, or any user-facing text.
  Triggers: code generation, comment writing, commit message, ADO work item, description formatting, coding standards.
---

# Project Guidelines & Standards

These guidelines must be followed for all changes in this project.

## 參考文件

| 文件 | 內容 |
|------|------|
| [references/vocabulary.md](references/vocabulary.md) | 英繁詞彙對照表（50+ 詞彙） |
| [references/ado-rules.md](references/ado-rules.md) | ADO Work Item 狀態流程、HTML 格式規範 |
| [references/code-examples.md](references/code-examples.md) | Python/TS/Dockerfile 翻譯 Before/After 範例 |

---

## 1. 語言要求（繁體中文）

**必須使用繁體中文的情境：**
- 程式碼註解（Python, TypeScript, Dockerfile 等）
- git commit 訊息
- 文件（README.md, *.md）
- 錯誤訊息與使用者面向文字
- ADO Task/PBI 描述
- 所有 AI 生成的實作計劃、推理過程

**例外（保留英文）：**
- 程式碼識別子（變數名、函式名、類別名、常數）
- 技術術語（FastMCP, Next.js, Docker, OAuth, Token）
- 國際開源貢獻

**識別子規則：** 維持英文命名，右側加繁中行內註解。
```python
# ✅ 正確
DEFAULT_TIMEOUT_MINUTES = 20  # 預設逾時時間（分鐘）

# ❌ 錯誤：不要翻譯識別子
預設逾時分鐘數 = 20
```

---

## 2. Python 程式碼規範

- 遵循 PEP 8
- 使用 type hinting
- 使用 `logger` 取代 `print`
- 所有函式與類別必須有繁體中文 Google Style docstring

**Docstring 格式：**
```python
def fetch_data(user_id: str) -> dict:
    """
    從 Genie API 獲取用戶數據。

    參數:
        user_id (str): 用戶的唯一標識符。

    回傳:
        dict: 包含用戶數據的字典。

    引發:
        ValueError: 如果 user_id 無效。
    """
```

**Async/Await：** 所有 I/O 操作（API 呼叫、DB 查詢）必須非同步；禁止 `time.sleep()`。

**Retry：** 所有 Databricks / Azure API 呼叫加 tenacity 重試（見 references/code-examples.md）。

**Import 順序：** Standard Library → Third Party → Local Application。

---

## 3. 錯誤處理

- 不暴露原始 stack trace 給使用者
- 完整錯誤記錄至 console/Application Insights
- 使用者面向訊息使用繁體中文

```python
# ✅ 正確
return "錯誤: 必須設定 DATABRICKS_HOST 環境變數。"

# ❌ 錯誤
return "Error: DATABRICKS_HOST must be set."
```

---

## 4. 環境變數與機密

- 禁止 hardcode（Workspace URL, PAT Token, Cluster ID 等）
- 使用 `os.environ` 或 `os.getenv`
- 新變數記錄在 `.env.example`
- 生產環境機密透過 **Azure Key Vault** 或 **Databricks Secrets** 管理

---

## 5. Git 規範

**Commit 訊息格式：**
```
type: 繁體中文描述
```
Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

範例：`feat: 新增登入功能`、`fix: 修復 Teams 連線問題`

**分支策略：**
- 所有新功能與修復先 commit 至 `develop`
- `main`/`master` 僅接受來自 `develop` 的 merge
- merge 進 `main` 一律使用 `--no-ff`

---

## 6. 文件分工

| 檔案 | 存放內容 |
|------|---------|
| `README.md` | 操作主來源：安裝、執行、部署步驟、環境變數清單 |
| `CLAUDE.md` | Agent 導航：範圍、關鍵規則、踩坑筆記 |

**原則：README.md 已是主來源，不重複貼進 CLAUDE.md。**

---

## 7. AuroraOps Actuator 安全防護

- Worker 數量下限 **2 台**、上限 **50 台**（從 `config/settings.yaml` 讀取，禁止 hardcode）
- **斷路器**：API 連續失敗或 AI 預測異常值時，退回安全預設值並發送警報
- **首次上線**：Dry-run 模式運行 2-3 天，僅 log 預計調整值，不發送 Edit Cluster API 請求

---

## 8. ADO Work Item

詳細規則見 [references/ado-rules.md](references/ado-rules.md)。

**快速參考：**
- Task 流程：`New → To Do → In Progress → Done`（禁止跳過）
- Description 格式：強制 HTML，禁止 Markdown
- 完成 Task：只填 `CompletedWork`，禁止設 `RemainingWork=0`
