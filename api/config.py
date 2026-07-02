from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    tracking_root: Path
    api_base_url: str


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def _discover_tracking_root(base_path: Path) -> Path:
    for candidate in (base_path, *base_path.parents):
        tracking_root = candidate / "AI_Tracking"
        if tracking_root.exists():
            return tracking_root

    return base_path / "AI_Tracking"


def _default_database_url(runtime_root: Path) -> str:
    data_root = runtime_root / "var"
    data_root.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_root / 'kl_observatory.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    runtime_root = _runtime_root()
    default_tracking_root = _discover_tracking_root(Path.cwd())
    if not default_tracking_root.exists():
        default_tracking_root = _discover_tracking_root(runtime_root)

    return Settings(
        app_name=os.getenv("APP_NAME", "KL Observatory"),
        database_url=os.getenv(
            "DATABASE_URL",
            _default_database_url(runtime_root),
        ),
        tracking_root=Path(
            os.getenv("TRACKING_ROOT", str(default_tracking_root))
        ).resolve(),
        api_base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
    )
