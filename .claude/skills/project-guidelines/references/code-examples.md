# 程式碼翻譯範例（Before / After）

## Python 函式 + 文件字串

**Before（英文原始）**

```python
# Load environment variables from .env file
load_dotenv()

def start_conversation(space_id: str, question: str) -> str:
    """
    Start a new conversation with Databricks Genie.

    Args:
        space_id: The Genie Space ID
        question: Natural language question to ask

    Returns:
        JSON string containing the conversation result
    """
    try:
        # Initialize workspace client
        w = WorkspaceClient()

        # Start conversation and wait for completion
        response = w.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question
        )

        return response.content

    except Exception as e:
        return f"Error starting conversation: {str(e)}"
```

**After（繁體中文規範）**

```python
# 載入 .env 環境變數
load_dotenv()

def start_conversation(space_id: str, question: str) -> str:
    """
    啟動與 Databricks Genie 的新對話。

    參數:
        space_id: Genie Space ID
        question: 要詢問的自然語言問題

    回傳:
        包含對話結果的 JSON 字串

    引發:
        Exception: 當 API 呼叫失敗時
    """
    try:
        # 初始化 workspace client
        w = WorkspaceClient()

        # 啟動對話並等待完成
        response = w.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question
        )

        return response.content

    except Exception as e:
        return f"啟動對話時發生錯誤: {str(e)}"
```

## TypeScript 函式

```typescript
// 為 Node.js 環境提供 EventSource polyfill
global.EventSource = EventSource;

/**
 * 取得所有可用的技能列表
 *
 * @returns 包含工具和提示的物件
 * @throws 當連線失敗時拋出錯誤
 */
export async function getSkills() {
  // 平行取得 Tools 和 Prompts
  const [tools, prompts] = await Promise.all([
    client.listTools(),
    client.listPrompts(),
  ]);
}
```

## Dockerfile 註解

```dockerfile
# 階段 1: 使用 UV 的建置階段
FROM python:3.12-slim AS builder

# 安裝 UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 複製依賴檔案並建立虛擬環境
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache .
```

## Python 使用 tenacity 重試

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_api():
    # 所有 Databricks / Azure API 呼叫皆應加此裝飾器
    ...
```
