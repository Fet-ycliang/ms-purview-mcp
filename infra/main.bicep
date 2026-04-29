targetScope = 'resourceGroup'

@minLength(1)
@maxLength(64)
param environmentName string

param location string = resourceGroup().location

@description('資源命名詞幹，用於產生資源名稱')
param resourceNameStem string = 'purview-mcp'

@description('現有 Container Registry 名稱（fetimageacr）')
param existingContainerRegistryName string = 'fetimageacr'

@description('現有 Container Apps Environment 名稱')
param existingContainerAppsEnvName string = 'cae-fet-outlook-email-env'

@description('現有 Container Apps Environment 所在的 Resource Group（若與本 RG 不同）')
param existingContainerAppsEnvResourceGroup string = ''

@description('Entra ID Tenant ID（Purview / Databricks 認證用）')
param azureTenantId string

@description('Service Principal Client ID')
param azureClientId string

@description('Service Principal Client Secret')
@secure()
param azureClientSecret string

@description('Microsoft Purview 帳號名稱')
param purviewAccountName string

@description('Databricks workspace URL（https://...）')
param databricksHost string

@description('Databricks PAT token')
@secure()
param databricksToken string

@description('Unity Catalog 預設 catalog 名稱')
param ucDefaultCatalog string = ''

@description('Unity Catalog catalog 清單（JSON 陣列字串）')
param ucCatalogs string = ''

@description('是否部署 APIM MCP API（Phase 3；ACA 部署完成後再設為 true）')
param deployApimMcpApi bool = false

@description('現有 APIM 服務名稱（deployApimMcpApi=true 時必填）')
param existingApimName string = ''

var abbrs = {
  containerApp: 'ca-'
  managedIdentity: 'id-'
}

var tags = {
  'azd-env-name': environmentName
  workload: 'purview-mcp'
  service: 'mcp'
  managed_by: 'azd'
}

var containerAppName = '${abbrs.containerApp}${resourceNameStem}'
var identityName = '${abbrs.managedIdentity}${resourceNameStem}'
var caeResourceGroup = !empty(existingContainerAppsEnvResourceGroup) ? existingContainerAppsEnvResourceGroup : resourceGroup().name

module resources 'resources.bicep' = {
  name: 'resources'
  params: {
    location: location
    tags: tags
    containerAppName: containerAppName
    identityName: identityName
    existingContainerRegistryName: existingContainerRegistryName
    existingContainerAppsEnvName: existingContainerAppsEnvName
    existingContainerAppsEnvResourceGroup: caeResourceGroup
    azureTenantId: azureTenantId
    azureClientId: azureClientId
    azureClientSecret: azureClientSecret
    purviewAccountName: purviewAccountName
    databricksHost: databricksHost
    databricksToken: databricksToken
    ucDefaultCatalog: ucDefaultCatalog
    ucCatalogs: ucCatalogs
  }
}

// ── Phase 3：APIM MCP API（deployApimMcpApi=true 時部署）────────────────────
// 警告：只新增 API，不修改既有 Named Values。在啟用前確認 existingApimName 正確。

module apimMcpApi 'modules/purview-mcp-apim-api.bicep' = if (deployApimMcpApi && !empty(existingApimName)) {
  name: 'purview-mcp-apim-api'
  params: {
    apimServiceName: existingApimName
    backendUrl: 'https://${resources.outputs.containerAppFqdn}/'
  }
}

output containerAppName string = resources.outputs.containerAppName
output containerAppFqdn string = resources.outputs.containerAppFqdn
output apimMcpUrl string = deployApimMcpApi && !empty(existingApimName) ? 'https://${existingApimName}.azure-api.net/purview-mcp/mcp' : ''
