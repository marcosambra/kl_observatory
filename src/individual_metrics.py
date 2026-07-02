from __future__ import annotations

from datetime import datetime
from typing import Any


def build_individual_metrics(overview: dict[str, Any]) -> dict[str, Any]:
    current_snapshot = overview.get("current_snapshot", {})
    counts = current_snapshot.get("counts", {}) if isinstance(current_snapshot, dict) else {}
    usage_events = overview.get("usage_events", [])
    sprint_metrics = _sorted_sprint_metrics(overview.get("sprint_metrics", []))
    open_prs = current_snapshot.get("open_prs", []) if isinstance(current_snapshot, dict) else []

    assigned_items = _safe_int(counts.get("assigned_items", 0))
    blocked_items = _safe_int(counts.get("blocked_items", 0))
    user_stories = _safe_int(counts.get("user_stories", 0))
    open_pr_count = _safe_int(counts.get("open_prs", len(open_prs)))
    remaining_story_points = _safe_float(current_snapshot.get("remaining_story_points", 0))
    remaining_work_hours = _safe_float(current_snapshot.get("remaining_work_hours", 0))
    actions_logged = sum(len(event.get("actions", [])) for event in usage_events)
    usage_sessions = len(usage_events)

    recent_story_points_burn = 0.0
    blocker_delta = 0
    if len(sprint_metrics) >= 2:
        previous_metric = sprint_metrics[-2]
        latest_metric = sprint_metrics[-1]
        recent_story_points_burn = round(
            max(
                _safe_float(previous_metric.get("remaining_story_points", 0))
                - _safe_float(latest_metric.get("remaining_story_points", 0)),
                0.0,
            ),
            1,
        )
        blocker_delta = _safe_int(latest_metric.get("blocked_items", 0)) - _safe_int(
            previous_metric.get("blocked_items", 0)
        )

    return {
        "user_email": current_snapshot.get("user_email") or "Active developer",
        "current": {
            "assigned_items": assigned_items,
            "blocked_items": blocked_items,
            "user_stories": user_stories,
            "open_pr_count": open_pr_count,
            "remaining_story_points": remaining_story_points,
            "remaining_work_hours": remaining_work_hours,
        },
        "derived": {
            "blocker_pressure_pct": round(
                (blocked_items / assigned_items) * 100,
                1,
            ) if assigned_items > 0 else 0.0,
            "review_load_per_item": round(
                open_pr_count / assigned_items,
                2,
            ) if assigned_items > 0 else float(open_pr_count),
            "remaining_hours_per_item": round(
                remaining_work_hours / assigned_items,
                1,
            ) if assigned_items > 0 else remaining_work_hours,
            "story_points_per_item": round(
                remaining_story_points / assigned_items,
                1,
            ) if assigned_items > 0 else remaining_story_points,
            "usage_sessions": usage_sessions,
            "actions_logged": actions_logged,
            "actions_per_session": round(
                actions_logged / usage_sessions,
                1,
            ) if usage_sessions > 0 else 0.0,
            "recent_story_points_burn": recent_story_points_burn,
            "blocker_delta": blocker_delta,
            "latest_usage_title": usage_events[-1].get("title", "n/a") if usage_events else "n/a",
            "latest_usage_timestamp": usage_events[-1].get("timestamp") if usage_events else None,
        },
    }


def _sorted_sprint_metrics(sprint_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(sprint_metrics, key=lambda item: _parse_timestamp(item.get("timestamp", "")))


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)
    if not normalized:
        return datetime.min
    return datetime.fromisoformat(normalized)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    return int(_safe_float(value))