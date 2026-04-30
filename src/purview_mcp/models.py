from __future__ import annotations

from typing import Any, Optional
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    azure_tenant_id: str = Field(
        validation_alias=AliasChoices("PURVIEW_TENANT_ID", "AZURE_TENANT_ID")
    )
    azure_client_id: str = Field(
        validation_alias=AliasChoices("PURVIEW_CLIENT_ID", "AZURE_CLIENT_ID")
    )
    azure_client_secret: str = Field(
        validation_alias=AliasChoices("PURVIEW_CLIENT_SECRET", "AZURE_CLIENT_SECRET")
    )
    purview_account_name: str

    databricks_host: str = ""
    databricks_token: Optional[str] = None
    databricks_client_id: Optional[str] = None
    databricks_client_secret: Optional[str] = None
    databricks_tenant_id: Optional[str] = None

    uc_default_catalog: str = "prod_catalog"
    uc_catalogs: list[str] = ["prod_catalog", "others_catalog"]

    @property
    def purview_base_url(self) -> str:
        return f"https://{self.purview_account_name}.purview.azure.com"

    @property
    def purview_tenant_id(self) -> str:
        return self.azure_tenant_id

    @property
    def purview_client_id(self) -> str:
        return self.azure_client_id

    @property
    def purview_client_secret(self) -> str:
        return self.azure_client_secret


class AssetResult(BaseModel):
    name: str
    qualified_name: str
    entity_type: str
    guid: Optional[str] = None
    description: Optional[str] = None
    labels: list[str] = []
    owner: Optional[str] = None
    experts: list[str] = []
    extra: dict[str, Any] = {}


class LineageNode(BaseModel):
    guid: str
    name: str
    entity_type: str
    qualified_name: Optional[str] = None


class LineageResult(BaseModel):
    base_entity_guid: str
    upstream: list[LineageNode] = []
    downstream: list[LineageNode] = []


class GlossaryTerm(BaseModel):
    name: str
    guid: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    status: Optional[str] = None
    examples: list[str] = []


class SensitivityLabel(BaseModel):
    label_name: str
    label_id: Optional[str] = None
    is_pii: bool = False


class ColumnDef(BaseModel):
    """Purview 端的欄位定義（從 databricks_table_column entity 解析）。"""
    name: str
    data_type: Optional[str] = None
    description: Optional[str] = None
    is_nullable: Optional[bool] = None
    ordinal_position: Optional[int] = None
    comment: Optional[str] = None
    guid: Optional[str] = None


class UCColumnInfo(BaseModel):
    name: str
    type_text: Optional[str] = None
    comment: Optional[str] = None
    nullable: bool = True


class UCTableInfo(BaseModel):
    catalog: str
    schema_name: str = Field(alias="schema")
    table_name: str
    table_type: Optional[str] = None
    comment: Optional[str] = None
    properties: dict[str, str] = {}
    columns: list[UCColumnInfo] = []

    model_config = {"populate_by_name": True}


class FieldComplianceResult(BaseModel):
    """欄位合規檢查結果。"""
    field_name: str
    compliant: bool
    suggestion: Optional[str] = None
    matched_term: Optional[str] = None
