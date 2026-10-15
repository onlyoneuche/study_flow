from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "StudyFlow"
    environment: Literal["development", "test", "production"] = "development"
    auth_secret: SecretStr = Field(min_length=32)
    database_url: str = "sqlite+aiosqlite:///./data/studyflow.db"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    ollama_base_url: HttpUrl = HttpUrl("http://localhost:11434")
    ollama_model: str = Field(default="qwen2.5:7b-instruct", min_length=1)
    ollama_health_timeout_seconds: float = Field(default=3, gt=0, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
