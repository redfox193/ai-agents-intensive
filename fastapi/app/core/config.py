from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки сервиса linksvc (значения из окружения или `.env`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["local", "testing", "production"] = "local"
    DEBUG: bool = True
    PROJECT_NAME: str = "Link Service"
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    DATABASE_URL: str = "postgresql+psycopg://app:app@localhost:5432/app"
    BASE_URL: str = "http://127.0.0.1:8000"
    CODE_LENGTH: int = 7


@lru_cache
def get_settings() -> Settings:
    """Кэшированная функция фабрики настроек для внедрения зависимостей."""
    return Settings()


settings = get_settings()
