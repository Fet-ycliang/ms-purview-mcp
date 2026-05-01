// 在現有 APIM 上新增 ms-purview-mcp API
// OAuth 由 mcp-oauth API 負責，PRM 的 authorization_servers 指向 {{APIMGatewayURL}}/ms-purview-mcp-oauth
// 不建立任何 Named Values（複用 outlook-email 已建立的 McpTenantId、McpClientId 等）

@description('現有 APIM 服務名稱')
param apimServiceName string

@description('purview-mcp ACA 的 backend URL（含尾端斜線），例如 https://ms-purview-mcp-ca.xxx.azurecontainerapps.io/')
param backendUrl string

resource apimService 'Microsoft.ApiManagement/service@2023-05-01-preview' existing = {
  name: apimServiceName
}

// ── ms-purview-mcp API ────────────────────────────────────────────────────────
// path 設為 'ms-purview-mcp'，對應 URL：<apim-gateway>/ms-purview-mcp/mcp

resource msPurviewMcpApi 'Microsoft.ApiManagement/service/apis@2023-05-01-preview' = {
  parent: apimService
  name: 'ms-purview-mcp'
  properties: {
    displayName: 'ms-purview-mcp API'
    description: 'Model Context Protocol API for Microsoft Purview data governance (Databricks Unity Catalog integration)'
    subscriptionRequired: false
    path: 'ms-purview-mcp'
    protocols: [
      'https'
    ]
    serviceUrl: backendUrl
  }
}

// ── JWT 驗證 policy fragment（可跨 API 複用）──────────────────────────────────

resource mcpJwtAuthFragment 'Microsoft.ApiManagement/service/policyFragments@2023-05-01-preview' = {
  parent: apimService
  name: 'mcp-jwt-auth'
  properties: {
    format: 'rawxml'
    value: loadTextContent('mcp-jwt-auth.fragment.xml')
    description: 'MCP JWT auth: Bearer 驗證、scope/role 檢查、Managed Identity 後端 token 注入'
  }
}

// ── API-level policy（引用 fragment，保留 backend / outbound / on-error）────────

resource msPurviewMcpApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'policy'
  dependsOn: [mcpJwtAuthFragment]
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-api.policy.xml')
  }
}

// ── MCP 主要端點 ──────────────────────────────────────────────────────────────

resource getMcpOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-streamable-get'
  properties: {
    displayName: 'ms-purview-mcp Streamable GET Endpoint'
    method: 'GET'
    urlTemplate: '/mcp'
    description: 'Streamable GET endpoint for ms-purview-mcp Server (SSE)'
  }
}

resource postMcpOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-streamable-post'
  properties: {
    displayName: 'ms-purview-mcp Streamable POST Endpoint'
    method: 'POST'
    urlTemplate: '/mcp'
    description: 'Streamable POST endpoint for ms-purview-mcp Server (JSON-RPC)'
  }
}

// ── OAuth discovery 端點 ──────────────────────────────────────────────────────

resource prmOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-prm'
  properties: {
    displayName: 'ms-purview-mcp Protected Resource Metadata'
    method: 'GET'
    urlTemplate: '/.well-known/oauth-protected-resource'
    description: 'Protected Resource Metadata endpoint (RFC 9728) for ms-purview-mcp'
  }
}

// ── Operation policies ────────────────────────────────────────────────────────

resource prmPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: prmOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-prm.policy.xml')
  }
}
