from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    tracking_root: Path
    api_base_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    workspace_root = Path(__file__).resolve().parents[3]
    default_tracking_root = workspace_root / "AI_Tracking"

    return Settings(
        app_name=os.getenv("APP_NAME", "KL Observatory"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://kl_observatory:kl_observatory@localhost:5432/kl_observatory",
        ),
        tracking_root=Path(
            os.getenv("TRACKING_ROOT", str(default_tracking_root))
        ).resolve(),
        api_base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
    )
