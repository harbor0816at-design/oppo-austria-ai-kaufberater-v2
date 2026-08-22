from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    admin_api_key: str = "change-me"
    database_url: str = "sqlite:////tmp/oppo_kaufberater.db"
    redis_url: str | None = None

    persistence_url: str = (
        "https://psnbcpgptrakpxbeptyb.supabase.co/functions/v1/"
        "kaufberater-persistence"
    )

    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_reasoning_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"

    brave_search_api_key: str | None = None

    # Source_B master data. Google Sheets is the source of truth.
    source_b_provider: str = "google_sheets"
    google_sheets_spreadsheet_id: str = "1OWEWh1--R6txBCkVRlKXB5xGER4AGMXm2ldgHKGayYc"
    google_service_account_json: str | None = None
    google_service_account_json_b64: str | None = None
    google_sheets_products_range: str = "Products!A1:AG2000"
    google_sheets_promotions_range: str = "Promotions!A1:T1000"
    google_sheets_services_range: str = "Services!A1:L500"
    google_sheets_cache_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    google_sheets_fail_open: bool = True

    chat_rate_limit_per_minute: int = Field(default=30, ge=1, le=300)
    lead_rate_limit_per_hour: int = Field(default=10, ge=1, le=200)
    analytics_rate_limit_per_minute: int = Field(default=120, ge=10, le=1000)

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8080",
        ]
    )
    session_ttl_seconds: int = Field(default=86_400, ge=300)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def admin_key_secure(self) -> bool:
        value = (self.admin_api_key or "").strip()
        return bool(value and value != "change-me" and len(value) >= 24)

    @property
    def remote_persistence_enabled(self) -> bool:
        return bool(self.persistence_url.strip() and self.admin_key_secure)

    @property
    def database_persistent(self) -> bool:
        return not self.database_url.lower().startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
