from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "AIAT Dashboard Final"
    app_env: str = "local"
    database_url: str = "sqlite:///./data/runtime/dashboard.sqlite"
    public_data_values_enabled: bool = False
    allow_pending_owner_sources: bool = False
    snapshot_root: Path = Path("./data/snapshots")
    max_records_per_source: int = 10_000
    http_timeout_seconds: float = 45.0
    http_delay_seconds: float = 0.25
    sra_year: str = "2569"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod", "railway"}

    @property
    def resolved_snapshot_root(self) -> Path:
        path = self.snapshot_root
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def raw_root(self) -> Path:
        return PROJECT_ROOT / "data" / "runtime" / "raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()
