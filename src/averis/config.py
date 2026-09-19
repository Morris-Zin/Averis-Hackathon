from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AVERIS_", env_file=".env", extra="ignore"
    )
    env: str = "development"
    database_url: str = "sqlite:///.local/averis.db"
    origin: str = "http://localhost:8000"
    storage_backend: str = "local"
    storage_dir: str = ".local/documents"
    r2_endpoint: str = ""
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    tasks_queue: str = ""
    worker_url: str = ""
    tasks_service_account: str = ""
    operator_token: str = ""
    live_enabled: bool = False
    budget_verified: bool = False
    prior_spend_usd: str = "0"
    input_usd_per_million: str = "0"
    output_usd_per_million: str = "0"
    typesafe_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="TYPESAFE_API_KEY"
    )
    jev_model: str = "jev-1.13.0"
    category_threshold: float = Field(default=0.80, ge=0, le=1)
    spam_threshold: float = Field(default=0.95, ge=0, le=1)
    field_threshold: float = Field(default=0.80, ge=0, le=1)
    frontend_dir: str = "apps/web/out"

    def validate_deployment(self) -> None:
        if self.env == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if not self.origin.startswith("https://"):
                raise ValueError("Production requires an HTTPS origin")
            if self.storage_backend != "r2":
                raise ValueError("Production requires private R2 storage")
