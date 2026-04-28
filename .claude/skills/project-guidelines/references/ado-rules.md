# Azure DevOps Work Item 管理規範

## Task 狀態轉換流程（強制執行）

```
New → To Do → In Progress → Done
```

| 步驟 | 狀態 | 說明 |
|------|------|------|
| 1 | New | Task 剛建立時的初始狀態（自動） |
| 2 | To Do | 確認進入 Sprint，準備開始 |
| 3 | In Progress | 正在進行開發/測試/部署 |
| 4 | Done | 工作完全完成，驗收通過 |

**禁止行為：**
- ❌ 建立 Task 時直接設為 Done（ADO 不支援，且違反流程）
- ❌ 從 To Do 直接跳到 Done（必須經過 In Progress）
- ❌ 使用 `wit_add_child_work_items`（Area Path 權限問題，改用三步驟流程）

**正確建立與完成 Task 的流程：**
```
步驟 1：wit_create_work_item（帶 System.AreaPath，狀態為預設 To Do）
步驟 2：wit_work_items_link（批次建立 parent 連結）
步驟 3：wit_update_work_item → 狀態改為 In Progress
步驟 4：wit_update_work_item → 狀態改為 Done，填入 CompletedWork
```

## PBI 狀態（Product Backlog Item）

```
New → Approved → Committed → Done
```

**注意**：PBI 的 `Effort`（故事點數）在 Done 狀態下為唯讀，須在 New/Approved 階段設定。

完成 Task 時只填 `CompletedWork`；**禁止設 `RemainingWork=0`**（ADO 不允許，會報 `InvalidNotEmpty`）。

## ADO 描述格式（強制 HTML）

`System.Description` 欄位**必須使用 HTML**，禁止純文字 Markdown。

```html
<!-- ✅ 正確 -->
<p>完成步驟一。</p>
<h3>驗收條件</h3>
<ul><li>Dockerfile 建置成功</li><li>/health 回 200</li></ul>

<!-- ❌ 錯誤：ADO 不渲染 Markdown -->
## 驗收條件
- Dockerfile 建置成功
```

## ADO Work Item 引用 URL

```
https://dev.azure.com/FET-IDTT/5c1d1372-d7f9-44cb-a3df-42a44a0cc770/_workitems/edit/{id}
```
