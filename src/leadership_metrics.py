from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any


def build_leadership_metrics(
    overview: dict[str, Any],
    assumptions: dict[str, float],
) -> dict[str, Any]:
    sprint_metrics = _sorted_sprint_metrics(overview)
    current_snapshot = overview.get("current_snapshot", {})
    counts = current_snapshot.get("counts", {}) if isinstance(current_snapshot, dict) else {}
    usage_events = overview.get("usage_events", [])
    open_prs = current_snapshot.get("open_prs", []) if isinstance(current_snapshot, dict) else []

    remaining_story_points = _latest_remaining_story_points(current_snapshot, sprint_metrics)
    planned_story_points = _planned_story_points(current_snapshot, sprint_metrics)
    actual_spent_story_points = round(
        max(planned_story_points - remaining_story_points, 0.0),
        1,
    )

    elapsed_sprint_pct = _safe_float(
        current_snapshot.get("sprint_elapsed_pct", assumptions["sprint_elapsed_pct"])
    )
    expected_spent_story_points = round(planned_story_points * elapsed_sprint_pct, 1)
    burn_variance_story_points = round(
        actual_spent_story_points - expected_spent_story_points,
        1,
    )
    burn_efficiency_pct = round(
        (actual_spent_story_points / expected_spent_story_points) * 100,
        1,
    ) if expected_spent_story_points > 0 else 0.0

    assigned_items = _safe_int(counts.get("assigned_items", 0))
    blocked_items = _safe_int(
        counts.get("blocked_items", _latest_blocked_items(sprint_metrics))
    )
    open_pr_count = _safe_int(counts.get("open_prs", len(open_prs)))
    average_pr_age_days = round(
        mean(_safe_float(pull_request.get("age_days", 0)) for pull_request in open_prs),
        1,
    ) if open_prs else 0.0
    blocked_scope_pct = round(
        (blocked_items / assigned_items) * 100,
        1,
    ) if assigned_items > 0 else 0.0
    review_pressure_pct = round(
        min(
            100.0,
            (open_pr_count / max(assumptions["target_open_prs"], 1.0)) * 100,
        ),
        1,
    )

    actions_logged = sum(len(event.get("actions", [])) for event in usage_events)
    actions_per_event = round(
        actions_logged / max(len(usage_events), 1),
        1,
    ) if usage_events else 0.0

    completion_pct = round(
        (actual_spent_story_points / planned_story_points) * 100,
        1,
    ) if planned_story_points > 0 else 0.0
    expected_completion_pct = round(elapsed_sprint_pct * 100, 1)
    scope_at_risk_story_points = round(max(expected_spent_story_points - actual_spent_story_points, 0.0), 1)
    forecast_delivered_story_points = round(
        min(
            planned_story_points,
            actual_spent_story_points / elapsed_sprint_pct,
        ),
        1,
    ) if elapsed_sprint_pct > 0 else actual_spent_story_points

    delivery_confidence_pct = _clamp(
        100.0
        - (scope_at_risk_story_points * 8.0)
        - (blocked_items * 10.0)
        - (max(average_pr_age_days - assumptions["pr_review_sla_days"], 0.0) * 6.0),
        0.0,
        100.0,
    )
    work_in_progress_items = assigned_items + open_pr_count

    return {
        "assumptions": {
            "sprint_elapsed_pct": elapsed_sprint_pct,
            "target_open_prs": assumptions["target_open_prs"],
            "pr_review_sla_days": assumptions["pr_review_sla_days"],
        },
        "tech_lead": {
            "planned_story_points": planned_story_points,
            "actual_spent_story_points": actual_spent_story_points,
            "expected_spent_story_points": expected_spent_story_points,
            "burn_variance_story_points": burn_variance_story_points,
            "burn_efficiency_pct": burn_efficiency_pct,
            "blocked_scope_pct": blocked_scope_pct,
            "average_pr_age_days": average_pr_age_days,
            "actions_per_event": actions_per_event,
            "blocked_items": blocked_items,
            "open_pr_count": open_pr_count,
        },
        "manager": {
            "completion_pct": completion_pct,
            "expected_completion_pct": expected_completion_pct,
            "remaining_story_points": remaining_story_points,
            "scope_at_risk_story_points": scope_at_risk_story_points,
            "forecast_delivered_story_points": forecast_delivered_story_points,
            "delivery_confidence_pct": round(delivery_confidence_pct, 1),
            "review_pressure_pct": review_pressure_pct,
            "work_in_progress_items": work_in_progress_items,
            "open_pr_count": open_pr_count,
            "blocked_items": blocked_items,
        },
    }


def _sorted_sprint_metrics(overview: dict[str, Any]) -> list[dict[str, Any]]:
    sprint_metrics = overview.get("sprint_metrics", [])
    return sorted(sprint_metrics, key=lambda item: _parse_timestamp(item.get("timestamp", "")))


def _latest_remaining_story_points(
    current_snapshot: dict[str, Any],
    sprint_metrics: list[dict[str, Any]],
) -> float:
    current_remaining = _safe_float(current_snapshot.get("remaining_story_points", 0))
    if current_remaining > 0:
        return current_remaining

    if sprint_metrics:
        return _safe_float(sprint_metrics[-1].get("remaining_story_points", 0))

    return current_remaining


def _planned_story_points(
    current_snapshot: dict[str, Any],
    sprint_metrics: list[dict[str, Any]],
) -> float:
    values = [_safe_float(current_snapshot.get("remaining_story_points", 0))]
    values.extend(_safe_float(item.get("remaining_story_points", 0)) for item in sprint_metrics)
    return round(max(values, default=0.0), 1)


def _latest_blocked_items(sprint_metrics: list[dict[str, Any]]) -> int:
    if not sprint_metrics:
        return 0
    return _safe_int(sprint_metrics[-1].get("blocked_items", 0))


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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))