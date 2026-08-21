from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
