from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    purview_account_name: str

    databricks_host: str = ""
    databricks_token: Optional[str] = None
    databricks_client_id: Optional[str] = None
    databricks_client_secret: Optional[str] = None
    databricks_tenant_id: Optional[str] = None

    uc_default_catalog: str = "main"

    @property
    def purview_base_url(self) -> str:
        return f"https://{self.purview_account_name}.purview.azure.com"


class AssetResult(BaseModel):
    name: str
    qualified_name: str
    entity_type: str
    guid: Optional[str] = None
    description: Optional[str] = None
    labels: list[str] = []
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
