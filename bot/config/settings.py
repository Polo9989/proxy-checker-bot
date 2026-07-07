"""
Application settings loaded from environment variables via pydantic-settings.
"""
from __future__ import annotations

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────
    bot_token: str = Field(..., description="Telegram bot token")

    # ── Checker defaults ─────────────────────────────────
    default_timeout: float = Field(10.0, ge=1, le=120)
    default_concurrency: int = Field(500, ge=1, le=2000)
    default_retries: int = Field(2, ge=0, le=5)
    default_test_url: str = Field("https://httpbin.org/ip")
    default_max_workers: int = Field(1000, ge=1, le=5000)

    # ── Limits ───────────────────────────────────────────
    max_proxies_per_user: int = Field(100_000, ge=100)
    max_file_size_mb: int = Field(50, ge=1, le=200)

    # ── Paths ─────────────────────────────────────────────
    database_path: Path = Field(Path("./data/bot.db"))
    output_dir: Path = Field(Path("./output"))
    log_file: Path = Field(Path("./logs/bot.log"))
    log_level: str = Field("INFO")

    @field_validator("output_dir", "database_path", "log_file", mode="before")
    @classmethod
    def ensure_parent(cls, v: str | Path) -> Path:
        p = Path(v)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()  # type: ignore[call-arg]
