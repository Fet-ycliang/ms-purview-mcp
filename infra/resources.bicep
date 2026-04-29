param location string
param tags object
param containerAppName string
param identityName string
param existingContainerRegistryName string
param existingContainerAppsEnvName string
param existingContainerAppsEnvResourceGroup string
param bootstrapContainerImage string

param azureTenantId string
param azureClientId string
@secure()
param azureClientSecret string

param purviewAccountName string
param databricksHost string
@secure()
param databricksToken string
param ucDefaultCatalog string
param ucCatalogs string

// ── 現有資源 reference ────────────────────────────────────────────────────────

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: existingContainerRegistryName
}

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: existingContainerAppsEnvName
  scope: resourceGroup(existingContainerAppsEnvResourceGroup)
}

// ── Managed Identity ──────────────────────────────────────────────────────────

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

// ACR Pull 角色指派（讓 identity 可以 pull image）
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, identity.id, acrPullRoleId)
  scope: containerRegistry
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ── Container App ─────────────────────────────────────────────────────────────
// 初次 provision 先用 public bootstrap image 建立 ACA，之後由 azd deploy 更新成實際 image。

var containerImage = bootstrapContainerImage

var containerSecrets = [
  {
    name: 'azure-client-secret'
    value: azureClientSecret
  }
  {
    name: 'databricks-token'
    value: databricksToken
  }
]

var ucCatalogList = !empty(ucCatalogs) ? split(replace(ucCatalogs, ' ', ''), ',') : []

var containerEnvVars = concat(
  [
    { name: 'USE_HTTP',   value: 'true' }
    { name: 'PORT',       value: '8080' }
    // Runtime auth is Purview-specific. Keep deploy auth separate from app auth.
    { name: 'PURVIEW_TENANT_ID', value: azureTenantId }
    { name: 'PURVIEW_CLIENT_ID', value: azureClientId }
    { name: 'PURVIEW_CLIENT_SECRET', secretRef: 'azure-client-secret' }
    { name: 'PURVIEW_ACCOUNT_NAME', value: purviewAccountName }
    { name: 'DATABRICKS_HOST', value: databricksHost }
    { name: 'DATABRICKS_TOKEN', secretRef: 'databricks-token' }
  ],
  !empty(ucDefaultCatalog) ? [{ name: 'UC_DEFAULT_CATALOG', value: ucDefaultCatalog }] : [],
  length(ucCatalogList) > 0 ? [{ name: 'UC_CATALOGS', value: string(ucCatalogList) }] : []
)

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'purview-mcp' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'http'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      maxInactiveRevisions: 5
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: containerSecrets
    }
    template: {
      containers: [
        {
          name: 'main'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: containerEnvVars
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
      }
    }
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output identityClientId string = identity.properties.clientId
