from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    admin_api_key: str = "change-me"
    database_url: str = "sqlite:////tmp/oppo_kaufberater.db"
    redis_url: str | None = None

    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_reasoning_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"

    brave_search_api_key: str | None = None
    blob_read_write_token: str | None = None
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

    @field_validator("deepseek_base_url")
    @classmethod
    def require_direct_deepseek_endpoint(cls, value: str) -> str:
        if value.rstrip("/") != "https://api.deepseek.com":
            raise ValueError("DEEPSEEK_BASE_URL must be https://api.deepseek.com")
        return "https://api.deepseek.com"

    @field_validator("deepseek_model")
    @classmethod
    def require_deepseek_flash_model(cls, value: str) -> str:
        if value != "deepseek-v4-flash":
            raise ValueError("DEEPSEEK_MODEL must be deepseek-v4-flash")
        return value

    @field_validator("deepseek_reasoning_model")
    @classmethod
    def require_deepseek_reasoning_model(cls, value: str) -> str:
        if value != "deepseek-v4-pro":
            raise ValueError("DEEPSEEK_REASONING_MODEL must be deepseek-v4-pro")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @model_validator(mode="after")
    def require_production_secrets(self) -> "Settings":
        if self.is_production and not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required in production")
        if self.is_production and self.admin_api_key == "change-me":
            raise ValueError("ADMIN_API_KEY must be changed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
