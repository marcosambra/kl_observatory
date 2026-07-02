from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from src.models import CurrentSprintSnapshot, SprintMetric, UsageEvent
from src.parsers import (
    load_current_sprint,
    read_sprint_metrics,
    read_usage_events,
    serialize_current_sprint,
    serialize_sprint_metric,
    serialize_usage_event,
)


def _tracking_status(root: Path) -> dict[str, object]:
    expected_paths = {
        "usage_log": root / "Metrics" / "ai-usage-log.md",
        "sprint_metrics": root / "Metrics" / "sprint-metrics.md",
        "current_sprint": root / "Task_Control" / "current-sprint.json",
        "daily_logs": root / "Daily_Action_Logs",
    }
    entries: list[dict[str, object]] = []
    missing_paths: list[str] = []

    for name, path in expected_paths.items():
        exists = path.exists()
        if not exists:
            missing_paths.append(str(path))
        entries.append(
            {
                "name": name,
                "path": str(path),
                "exists": exists,
            }
        )

    return {
        "root": str(root),
        "available": not missing_paths,
        "missing_paths": missing_paths,
        "entries": entries,
    }


def build_tracking_overview(
    tracking_root: Path | None = None,
    log_limit: int = 5,
) -> dict:
    settings = get_settings()
    root = tracking_root or settings.tracking_root
    status = _tracking_status(root)

    usage_log_path = root / "Metrics" / "ai-usage-log.md"
    sprint_metrics_path = root / "Metrics" / "sprint-metrics.md"
    current_sprint_path = root / "Task_Control" / "current-sprint.json"

    usage_events = read_usage_events(usage_log_path) if usage_log_path.exists() else []
    sprint_metrics = (
        read_sprint_metrics(sprint_metrics_path)
        if sprint_metrics_path.exists()
        else []
    )
    current_sprint = (
        load_current_sprint(current_sprint_path)
        if current_sprint_path.exists()
        else None
    )

    daily_logs: list[dict[str, str]] = []
    daily_logs_root = root / "Daily_Action_Logs"
    if daily_logs_root.exists():
        for log_path in sorted(daily_logs_root.glob("*.md"), reverse=True)[:log_limit]:
            daily_logs.append(
                {
                    "name": log_path.name,
                    "content": log_path.read_text(encoding="utf-8"),
                }
            )

    return {
        "current_snapshot": (
            serialize_current_sprint(current_sprint) if current_sprint else {}
        ),
        "usage_events": [serialize_usage_event(record) for record in usage_events],
        "sprint_metrics": [serialize_sprint_metric(record) for record in sprint_metrics],
        "daily_logs": daily_logs,
        "tracking_status": status,
    }


def sync_tracking_data(session: Session, tracking_root: Path | None = None) -> dict:
    overview = build_tracking_overview(tracking_root=tracking_root, log_limit=10)

    usage_synced = 0
    for record in overview["usage_events"]:
        existing = session.scalar(
            select(UsageEvent).where(UsageEvent.source_key == record["source_key"])
        )
        if existing is None:
            session.add(
                UsageEvent(
                    source_key=record["source_key"],
                    timestamp=record["timestamp"],
                    title=record["title"],
                    summary=record["summary"],
                    remaining_story_points=record["remaining_story_points"],
                    blocked_items=record["blocked_items"],
                    actions=record["actions"],
                )
            )
            usage_synced += 1

    metrics_synced = 0
    for record in overview["sprint_metrics"]:
        existing = session.scalar(
            select(SprintMetric).where(SprintMetric.source_key == record["source_key"])
        )
        if existing is None:
            session.add(
                SprintMetric(
                    source_key=record["source_key"],
                    timestamp=record["timestamp"],
                    remaining_story_points=record["remaining_story_points"],
                    blocked_items=record["blocked_items"],
                    summary=record["summary"],
                )
            )
            metrics_synced += 1

    current_snapshot = overview.get("current_snapshot", {})
    current_snapshot_timestamp = current_snapshot.get("generated_at")
    snapshots_synced = 0

    if current_snapshot_timestamp:
        existing_snapshot = session.scalar(
            select(CurrentSprintSnapshot).where(
                CurrentSprintSnapshot.generated_at == current_snapshot_timestamp
            )
        )
        if existing_snapshot is None:
            session.add(
                CurrentSprintSnapshot(
                    generated_at=current_snapshot_timestamp,
                    project=current_snapshot.get("project", ""),
                    user_email=current_snapshot.get("user_email", ""),
                    assigned_items=current_snapshot.get("counts", {}).get("assigned_items", 0),
                    blocked_items=current_snapshot.get("counts", {}).get("blocked_items", 0),
                    open_prs=current_snapshot.get("counts", {}).get("open_prs", 0),
                    user_stories=current_snapshot.get("counts", {}).get("user_stories", 0),
                    remaining_story_points=current_snapshot.get("remaining_story_points", 0),
                    remaining_work_hours=current_snapshot.get("remaining_work_hours", 0),
                    raw_payload=current_snapshot,
                )
            )
            snapshots_synced = 1
        else:
            existing_snapshot.raw_payload = current_snapshot
            existing_snapshot.project = current_snapshot.get("project", "")
            existing_snapshot.user_email = current_snapshot.get("user_email", "")
            existing_snapshot.assigned_items = current_snapshot.get("counts", {}).get(
                "assigned_items", 0
            )
            existing_snapshot.blocked_items = current_snapshot.get("counts", {}).get(
                "blocked_items", 0
            )
            existing_snapshot.open_prs = current_snapshot.get("counts", {}).get(
                "open_prs", 0
            )
            existing_snapshot.user_stories = current_snapshot.get("counts", {}).get(
                "user_stories", 0
            )
            existing_snapshot.remaining_story_points = current_snapshot.get(
                "remaining_story_points", 0
            )
            existing_snapshot.remaining_work_hours = current_snapshot.get(
                "remaining_work_hours", 0
            )

    session.commit()

    return {
        "usage_events_synced": usage_synced,
        "sprint_metrics_synced": metrics_synced,
        "snapshots_synced": snapshots_synced,
        "current_snapshot": current_snapshot_timestamp,
        "tracking_status": overview["tracking_status"],
    }


def get_persisted_summary(session: Session) -> dict:
    usage_count = session.scalar(select(func.count()).select_from(UsageEvent)) or 0
    sprint_count = session.scalar(select(func.count()).select_from(SprintMetric)) or 0
    snapshot_count = session.scalar(
        select(func.count()).select_from(CurrentSprintSnapshot)
    ) or 0
    latest_snapshot = session.scalar(
        select(CurrentSprintSnapshot.generated_at)
        .order_by(CurrentSprintSnapshot.generated_at.desc())
        .limit(1)
    )

    return {
        "usage_events_synced": usage_count,
        "sprint_metrics_synced": sprint_count,
        "snapshots_synced": snapshot_count,
        "latest_snapshot": latest_snapshot.isoformat() if latest_snapshot else None,
    }
