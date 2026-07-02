from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .database import SessionLocal, init_db
from .services import (
    build_tracking_overview,
    get_persisted_summary,
    refresh_tracking_from_azure_agent,
    sync_tracking_data,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/overview")
def overview() -> dict:
    with SessionLocal() as session:
        tracking_overview = build_tracking_overview()
        tracking_overview["persisted"] = get_persisted_summary(session)
        return tracking_overview


@app.get("/status")
def status() -> dict:
    tracking_overview = build_tracking_overview(log_limit=0)
    return tracking_overview["tracking_status"]


@app.post("/sync")
def sync() -> dict:
    with SessionLocal() as session:
        sync_result = sync_tracking_data(session)
        sync_result["persisted"] = get_persisted_summary(session)
        return sync_result


@app.post("/refresh/azure")
def refresh_azure() -> dict:
    with SessionLocal() as session:
        return refresh_tracking_from_azure_agent(session)
