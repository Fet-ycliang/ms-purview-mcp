// 在現有 APIM 上新增 purview-mcp API
// 注意：不建立任何 Named Values（複用 outlook-email 已建立的 McpTenantId、McpClientId 等）
// 只新增 API 定義、operations 和 policy，不修改任何既有 APIM 資源

@description('現有 APIM 服務名稱')
param apimServiceName string

@description('purview-mcp ACA 的 backend URL（含尾端斜線），例如 https://ms-purview-mcp-ca.xxx.azurecontainerapps.io/')
param backendUrl string

resource apimService 'Microsoft.ApiManagement/service@2023-05-01-preview' existing = {
  name: apimServiceName
}

// ── Purview MCP API ───────────────────────────────────────────────────────────
// path 設為 'purview-mcp'，對應 URL：<apim-gateway>/purview-mcp/mcp
// 不影響既有 outlook-email API（其 path 為 '/'）

resource purviewMcpApi 'Microsoft.ApiManagement/service/apis@2023-05-01-preview' = {
  parent: apimService
  name: 'purview-mcp'
  properties: {
    displayName: 'Purview MCP API'
    description: 'Model Context Protocol API for Microsoft Purview data governance (Databricks Unity Catalog integration)'
    subscriptionRequired: false
    path: 'purview-mcp'
    protocols: [
      'https'
    ]
    serviceUrl: backendUrl
  }
}

// ── API-level policy（JWT 驗證 + 後端 token 注入）─────────────────────────────
// 複用 APIM 中既有的 Named Values：McpTenantId、McpClientId、McpAppIdUri、
// BackendMcpAppIdUri、ApimBackendClientId、McpAllowedCallerAppIdsCsv 等

resource purviewMcpApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-05-01-preview' = {
  parent: purviewMcpApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('purview-mcp-api.policy.xml')
  }
}

// ── Operations ────────────────────────────────────────────────────────────────

resource getMcpOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: purviewMcpApi
  name: 'purview-mcp-streamable-get'
  properties: {
    displayName: 'Purview MCP Streamable GET Endpoint'
    method: 'GET'
    urlTemplate: '/mcp'
    description: 'Streamable GET endpoint for Purview MCP Server (SSE)'
  }
}

resource postMcpOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: purviewMcpApi
  name: 'purview-mcp-streamable-post'
  properties: {
    displayName: 'Purview MCP Streamable POST Endpoint'
    method: 'POST'
    urlTemplate: '/mcp'
    description: 'Streamable POST endpoint for Purview MCP Server (JSON-RPC)'
  }
}

resource prmOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: purviewMcpApi
  name: 'purview-mcp-prm'
  properties: {
    displayName: 'Purview MCP Protected Resource Metadata'
    method: 'GET'
    urlTemplate: '/.well-known/oauth-protected-resource'
    description: 'Protected Resource Metadata endpoint (RFC 9728) for Purview MCP'
  }
}

// ── PRM operation policy（回傳 purview-mcp 專屬 resource URL）────────────────

resource prmPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: prmOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('purview-mcp-prm.policy.xml')
  }
}
