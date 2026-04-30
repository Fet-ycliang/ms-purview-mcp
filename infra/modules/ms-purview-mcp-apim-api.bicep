// 在現有 APIM 上新增 ms-purview-mcp API
// 獨立 OAuth server：所有 discovery metadata endpoint 均指向 ms-purview-mcp/*，
// authorize / token / register 再 proxy 到既有 mcp-oauth 實作
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

// ── API-level policy（JWT 驗證 + 後端 token 注入）─────────────────────────────

resource msPurviewMcpApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'policy'
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

resource oauthAuthorizationServerOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-oauth-authorization-server'
  properties: {
    displayName: 'ms-purview-mcp OAuth Authorization Server Metadata'
    method: 'GET'
    urlTemplate: '/.well-known/oauth-authorization-server'
    description: 'OAuth authorization server metadata for ms-purview-mcp clients'
  }
}

resource oauthOpenIdConfigurationOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-oauth-openid-configuration'
  properties: {
    displayName: 'ms-purview-mcp OpenID Configuration'
    method: 'GET'
    urlTemplate: '/.well-known/openid-configuration'
    description: 'OpenID configuration metadata for ms-purview-mcp clients'
  }
}

// ── OAuth proxy 端點（proxy 至既有 mcp-oauth 實作）───────────────────────────

resource authorizeOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-authorize'
  properties: {
    displayName: 'ms-purview-mcp Authorize'
    method: 'GET'
    urlTemplate: '/authorize'
    description: 'OAuth authorization endpoint — 302 redirect proxy to mcp-oauth/authorize'
  }
}

resource tokenOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-token'
  properties: {
    displayName: 'ms-purview-mcp Token'
    method: 'POST'
    urlTemplate: '/token'
    description: 'OAuth token endpoint — proxy to mcp-oauth/token'
  }
}

resource registerOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: msPurviewMcpApi
  name: 'ms-purview-mcp-register'
  properties: {
    displayName: 'ms-purview-mcp Register'
    method: 'POST'
    urlTemplate: '/register'
    description: 'Dynamic client registration endpoint — proxy to mcp-oauth/register'
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

resource oauthAuthorizationServerPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: oauthAuthorizationServerOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-oauth-authorization-server.policy.xml')
  }
}

resource oauthOpenIdConfigurationPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: oauthOpenIdConfigurationOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-oauth-openid-configuration.policy.xml')
  }
}

resource authorizePolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: authorizeOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-authorize.policy.xml')
  }
}

resource tokenPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: tokenOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-token.policy.xml')
  }
}

resource registerPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: registerOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: loadTextContent('ms-purview-mcp-register.policy.xml')
  }
}
