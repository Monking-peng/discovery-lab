from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_name: str = "Discovery Lab API"
    api_prefix: str = "/v1"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://discovery:discovery_dev_only@127.0.0.1:5432/discovery_lab"
    )
    blob_root: Path = Path("./var/blobs")
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    evidence_extractor: Literal["demo", "openai"] = "demo"
    openai_model: str = "gpt-5.6-luna"
    openai_api_key: SecretStr | None = None
    evidence_prompt_version: str = "evidence-extraction.v1"
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
