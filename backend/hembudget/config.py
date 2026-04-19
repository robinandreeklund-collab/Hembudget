from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    override = os.environ.get("HEMBUDGET_DATA_DIR")
    if override:
        return Path(override)
    home = Path.home()
    if os.name == "nt":
        return home / "AppData" / "Roaming" / "Hembudget"
    if os.uname().sysname == "Darwin":
        return home / "Library" / "Application Support" / "Hembudget"
    return home / ".local" / "share" / "hembudget"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEMBUDGET_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default_factory=_default_data_dir)
    db_filename: str = "hembudget.db"

    host: str = "127.0.0.1"
    port: int = 0

    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm-studio"
    lm_studio_model: str = "nvidia/nemotron-3-nano"

    categorization_batch_size: int = 30
    llm_timeout_seconds: int = 120

    session_timeout_minutes: int = 30

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / self.db_filename


settings = Settings()
