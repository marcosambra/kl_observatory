from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from src.models import CurrentSprintSnapshot, SprintMetric, UsageEvent
from src.parsers import (
    load_current_sprint,
    parse_timestamp,
    read_sprint_metrics,
    read_usage_events,
    serialize_current_sprint,
    serialize_sprint_metric,
    serialize_usage_event,
)
from src.tracking_insights import (
    parse_optimization_report,
    parse_storypoints_report,
    summarize_audit_log,
    summarize_repo_work_item_context,
)


PORTUGUESE_SUMMARY_PATTERN = re.compile(
    r"Resumo do sprint para (?P<user_email>[^.]+)\. "
    r"Itens atribu[íi]dos: (?P<assigned_items>\d+)\. "
    r"Itens bloqueados: (?P<blocked_items>\d+)\. "
    r"Itens devolvidos detectados: (?P<returned_items>\d+)\. "
    r"Story points restantes: (?P<remaining_story_points>\d+)\. "
    r"PRs abertas: (?P<open_prs>\d+)\."
)

ENGLISH_SUMMARY_PATTERN = re.compile(
    r"with (?P<assigned_items>\d+) assigned items, "
    r"(?P<blocked_items>\d+) blocked items, and "
    r"(?P<open_prs>\d+) open PRs"
)


def _tracking_status(
    root: Path,
    derived_current_snapshot: dict[str, Any] | None = None,
) -> dict[str, object]:
    required_paths = {"usage_log", "sprint_metrics", "current_sprint", "daily_logs"}
    expected_paths = {
        "usage_log": root / "Metrics" / "ai-usage-log.md",
        "sprint_metrics": root / "Metrics" / "sprint-metrics.md",
        "optimization_report": root / "Metrics" / "AI_Optimization_Metrics_Report.md",
        "storypoints_report": root / "Metrics" / "AI_StoryPoints_Objective_Report.md",
        "current_sprint": root / "Task_Control" / "current-sprint.json",
        "current_sprint_markdown": root / "Task_Control" / "current-sprint.md",
        "daily_logs": root / "Daily_Action_Logs",
        "repo_work_item_context": root / "Repo_Work_Item_Context",
        "audit_log": root / "Audit" / "mcp-audit.log",
    }
    entries: list[dict[str, object]] = []
    missing_paths: list[str] = []

    for name, path in expected_paths.items():
        exists = path.exists()
        state = "present" if exists else "missing"

        if name == "current_sprint" and not exists and derived_current_snapshot:
            state = "derived"

        is_satisfied = exists or (name == "current_sprint" and derived_current_snapshot)
        if name in required_paths and not is_satisfied:
            missing_paths.append(str(path))
        entries.append(
            {
                "name": name,
                "path": str(path),
                "exists": exists,
                "state": state,
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

    usage_log_path = root / "Metrics" / "ai-usage-log.md"
    sprint_metrics_path = root / "Metrics" / "sprint-metrics.md"
    optimization_report_path = root / "Metrics" / "AI_Optimization_Metrics_Report.md"
    storypoints_report_path = root / "Metrics" / "AI_StoryPoints_Objective_Report.md"
    current_sprint_path = root / "Task_Control" / "current-sprint.json"
    current_sprint_markdown_path = root / "Task_Control" / "current-sprint.md"
    repo_work_item_context_root = root / "Repo_Work_Item_Context"
    audit_log_path = root / "Audit" / "mcp-audit.log"

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
    derived_current_snapshot = None
    if current_sprint is None:
        derived_current_snapshot = _derive_current_snapshot_from_metrics(
            sprint_metrics,
            usage_events,
        )

    status = _tracking_status(root, derived_current_snapshot=derived_current_snapshot)

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

    optimization_report = (
        parse_optimization_report(optimization_report_path.read_text(encoding="utf-8"))
        if optimization_report_path.exists()
        else {"content": "", "metrics": {}}
    )
    storypoints_report = (
        parse_storypoints_report(storypoints_report_path.read_text(encoding="utf-8"))
        if storypoints_report_path.exists()
        else {"content": "", "metrics": {}}
    )
    repo_work_item_context = (
        summarize_repo_work_item_context(repo_work_item_context_root)
        if repo_work_item_context_root.exists()
        else {
            "preview_summary": {"files": [], "total_preview_files": 0, "total_preview_entries": 0},
            "technical_debt_summary": {"files": [], "total_debt_files": 0, "total_items": 0, "state_counts": {}},
        }
    )
    audit_log = (
        summarize_audit_log(audit_log_path.read_text(encoding="utf-8"))
        if audit_log_path.exists()
        else {"summary": {}, "tail": []}
    )
    current_sprint_markdown = (
        current_sprint_markdown_path.read_text(encoding="utf-8")
        if current_sprint_markdown_path.exists()
        else ""
    )

    return {
        "current_snapshot": (
            serialize_current_sprint(current_sprint)
            if current_sprint
            else (derived_current_snapshot or {})
        ),
        "usage_events": [serialize_usage_event(record) for record in usage_events],
        "sprint_metrics": [serialize_sprint_metric(record) for record in sprint_metrics],
        "optimization_report": optimization_report,
        "storypoints_report": storypoints_report,
        "repo_work_item_context": repo_work_item_context,
        "audit_log": audit_log,
        "current_sprint_markdown": current_sprint_markdown,
        "daily_logs": daily_logs,
        "tracking_status": status,
    }


def _derive_current_snapshot_from_metrics(
    sprint_metrics: list[Any],
    usage_events: list[Any],
) -> dict[str, Any] | None:
    if not sprint_metrics:
        return None

    latest_metric = sprint_metrics[-1]
    summary = str(getattr(latest_metric, "summary", "") or "")
    timestamp = getattr(latest_metric, "timestamp", None)
    remaining_story_points = int(getattr(latest_metric, "remaining_story_points", 0) or 0)
    blocked_items = int(getattr(latest_metric, "blocked_items", 0) or 0)

    counts = {
        "assigned_items": 0,
        "blocked_items": blocked_items,
        "open_prs": 0,
        "user_stories": 0,
    }
    user_email = ""

    portuguese_match = PORTUGUESE_SUMMARY_PATTERN.search(summary)
    english_match = ENGLISH_SUMMARY_PATTERN.search(summary)

    if portuguese_match:
        user_email = portuguese_match.group("user_email").strip()
        counts["assigned_items"] = int(portuguese_match.group("assigned_items"))
        counts["blocked_items"] = int(portuguese_match.group("blocked_items"))
        counts["open_prs"] = int(portuguese_match.group("open_prs"))
        remaining_story_points = int(portuguese_match.group("remaining_story_points"))
    elif english_match:
        counts["assigned_items"] = int(english_match.group("assigned_items"))
        counts["blocked_items"] = int(english_match.group("blocked_items"))
        counts["open_prs"] = int(english_match.group("open_prs"))

    latest_usage_summary = ""
    latest_usage_title = ""
    if usage_events:
        latest_usage_event = usage_events[-1]
        latest_usage_summary = getattr(latest_usage_event, "summary", "")
        latest_usage_title = getattr(latest_usage_event, "title", "")

    return {
        "generated_at": timestamp.isoformat() if timestamp else None,
        "project": "",
        "user_email": user_email,
        "counts": counts,
        "remaining_story_points": remaining_story_points,
        "remaining_work_hours": 0,
        "open_prs": [],
        "items": [],
        "blocked_items": [],
        "returned_items": [],
        "snapshot_source": "derived_from_metrics",
        "summary": summary,
        "latest_usage_summary": latest_usage_summary,
        "latest_usage_title": latest_usage_title,
    }


def _normalize_generated_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str) and value.strip():
        return parse_timestamp(value)

    return None


def _resolve_observatory_refresh_script() -> Path:
    candidate_paths = [
        Path(__file__).resolve().parents[1] / "scripts" / "refresh_from_azure_agent.py",
        Path.cwd().resolve() / "scripts" / "refresh_from_azure_agent.py",
        Path("/app/scripts/refresh_from_azure_agent.py"),
    ]

    checked_paths: list[str] = []
    for candidate in candidate_paths:
        resolved = candidate.expanduser().resolve()
        checked_paths.append(str(resolved))
        if resolved.exists():
            return resolved

    raise FileNotFoundError(
        "Observatory Azure refresh script not found. Checked: " + ", ".join(checked_paths)
    )


def refresh_tracking_from_azure_agent(
    session: Session,
    *,
    source: str = "kl-observatory-dashboard",
    notify: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    refresh_script = _resolve_observatory_refresh_script()

    command = [str(Path(sys.executable)), str(refresh_script), "--source", source]
    if notify:
        command.append("--notify")

    completed = subprocess.run(
        command,
        cwd=str(settings.workspace_root),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        raise RuntimeError(stderr or stdout or "Azure agent refresh failed.")

    agent_refresh = json.loads(stdout) if stdout else {
        "source": source,
        "command": command,
        "stdout": "",
        "stderr": "",
        "returncode": 0,
    }

    sync_result = sync_tracking_data(session, tracking_root=settings.tracking_root)
    sync_result["persisted"] = get_persisted_summary(session)
    sync_result["agent_refresh"] = agent_refresh
    return sync_result


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
    normalized_generated_at = _normalize_generated_at(current_snapshot_timestamp)
    snapshots_synced = 0

    if normalized_generated_at is not None:
        existing_snapshot = session.scalar(
            select(CurrentSprintSnapshot).where(
                CurrentSprintSnapshot.generated_at == normalized_generated_at
            )
        )
        if existing_snapshot is None:
            session.add(
                CurrentSprintSnapshot(
                    generated_at=normalized_generated_at,
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
        "current_snapshot": (
            normalized_generated_at.isoformat()
            if normalized_generated_at is not None
            else current_snapshot_timestamp
        ),
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
