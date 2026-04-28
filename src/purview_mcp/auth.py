from azure.identity import ClientSecretCredential
from .models import Settings

# 注意：你們的 Purview 是早期版本，scope 用 .net 而非 .com
# Azure Purview Enterprise App 的 ServicePrincipalName: https://purview.azure.net/
_PURVIEW_SCOPE = "https://purview.azure.net/.default"

_credential: ClientSecretCredential | None = None


def _get_credential(settings: Settings) -> ClientSecretCredential:
    global _credential
    if _credential is None:
        _credential = ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
        )
    return _credential


def get_token(settings: Settings) -> str:
    """取得 Purview Bearer Token，azure-identity 自動處理刷新。"""
    credential = _get_credential(settings)
    token = credential.get_token(_PURVIEW_SCOPE)
    return token.token
