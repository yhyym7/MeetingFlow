from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEETINGFLOW_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MeetingFlow"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    display_timezone: str = "Asia/Shanghai"
    trusted_origins: list[str] = [
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:8000", "http://localhost:8000",
    ]
    database_url: SecretStr | None = None
    session_hours: int = Field(default=8, ge=1, le=168)
    cookie_secure: bool = False
    analysis_worker_enabled: bool = True
    analysis_mode: Literal["demo", "unconfigured", "deepseek"] = "demo"
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = "deepseek-flash"
    asr_mode: Literal["unconfigured", "local"] = "unconfigured"
    embedding_mode: Literal["keyword", "local"] = "keyword"
    model_dir: Path = BACKEND_DIR / "storage" / "models"
    asr_max_seconds: int = Field(default=600, ge=10, le=3600)
    audio_storage_dir: Path = BACKEND_DIR / "storage" / "audio"
    audio_max_mb: int = Field(default=50, ge=1, le=500)


@lru_cache
def get_settings() -> Settings:
    return Settings()
