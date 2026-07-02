from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any


def build_leadership_metrics(
    overview: dict[str, Any],
    assumptions: dict[str, float],
) -> dict[str, Any]:
    sprint_metrics = _sorted_sprint_metrics(overview)
    current_snapshot = overview.get("current_snapshot", {})
    counts = current_snapshot.get("counts", {}) if isinstance(current_snapshot, dict) else {}
    project_progress = current_snapshot.get("project_progress", {}) if isinstance(current_snapshot, dict) else {}
    child_summary = current_snapshot.get("child_items_summary", {}) if isinstance(current_snapshot, dict) else {}
    usage_events = overview.get("usage_events", [])
    open_prs = current_snapshot.get("open_prs", []) if isinstance(current_snapshot, dict) else []

    remaining_story_points = _latest_remaining_story_points(current_snapshot, sprint_metrics)
    planned_story_points = _planned_story_points(current_snapshot, sprint_metrics)
    actual_spent_story_points = round(
        max(planned_story_points - remaining_story_points, 0.0),
        1,
    )

    elapsed_sprint_pct, elapsed_source = _resolve_sprint_elapsed_pct(
        current_snapshot,
        assumptions,
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
    tasks_all_statuses = _safe_int(counts.get("tasks_all_statuses", 0))
    sprint_stories = _safe_int(counts.get("sprint_stories", 0))
    children_of_assigned_items = _safe_int(counts.get("children_of_assigned_items", 0))
    blocked_children_of_assigned_items = _safe_int(counts.get("blocked_children_of_assigned_items", 0))
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
    progress_by_story_count_pct = round(
        _safe_float(project_progress.get("progress_percent_by_story_count", completion_pct)),
        1,
    )
    progress_by_story_points_pct = round(
        _safe_float(project_progress.get("progress_percent_by_story_points", completion_pct)),
        1,
    )
    blocked_story_points = round(_safe_float(project_progress.get("blocked_story_points", 0)), 1)
    blocked_stories = _safe_int(project_progress.get("blocked_stories", 0))
    completed_children = _safe_int(child_summary.get("completed_children", 0))
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
            "elapsed_source": elapsed_source,
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
            "tasks_all_statuses": tasks_all_statuses,
            "sprint_stories": sprint_stories,
            "children_of_assigned_items": children_of_assigned_items,
            "blocked_children_of_assigned_items": blocked_children_of_assigned_items,
            "child_blocker_pressure_pct": round(
                (blocked_children_of_assigned_items / children_of_assigned_items) * 100,
                1,
            ) if children_of_assigned_items > 0 else 0.0,
            "blocked_story_points": blocked_story_points,
            "blocked_stories": blocked_stories,
        },
        "manager": {
            "completion_pct": completion_pct,
            "expected_completion_pct": expected_completion_pct,
            "progress_by_story_count_pct": progress_by_story_count_pct,
            "progress_by_story_points_pct": progress_by_story_points_pct,
            "remaining_story_points": remaining_story_points,
            "scope_at_risk_story_points": scope_at_risk_story_points,
            "forecast_delivered_story_points": forecast_delivered_story_points,
            "delivery_confidence_pct": round(delivery_confidence_pct, 1),
            "review_pressure_pct": review_pressure_pct,
            "work_in_progress_items": work_in_progress_items,
            "open_pr_count": open_pr_count,
            "blocked_items": blocked_items,
            "sprint_stories": sprint_stories,
            "children_of_assigned_items": children_of_assigned_items,
            "completed_children": completed_children,
            "blocked_children_of_assigned_items": blocked_children_of_assigned_items,
            "blocked_story_points": blocked_story_points,
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


def _resolve_sprint_elapsed_pct(
    current_snapshot: dict[str, Any],
    assumptions: dict[str, float],
) -> tuple[float, str]:
    snapshot_value = current_snapshot.get("sprint_elapsed_pct")
    if snapshot_value is not None:
        return _clamp(_safe_float(snapshot_value), 0.0, 1.0), "snapshot"

    sprint_context = current_snapshot.get("sprint_context", {})
    if isinstance(sprint_context, dict):
        start_at = _parse_optional_timestamp(sprint_context.get("start_date"))
        finish_at = _parse_optional_timestamp(sprint_context.get("finish_date"))
        reference_at = _resolve_reference_timestamp(current_snapshot)
        if start_at is not None and finish_at is not None and finish_at > start_at:
            if reference_at <= start_at:
                return 0.0, "sprint_context"
            if reference_at >= finish_at:
                return 1.0, "sprint_context"
            ratio = (reference_at - start_at).total_seconds() / (finish_at - start_at).total_seconds()
            return round(_clamp(ratio, 0.0, 1.0), 4), "sprint_context"

    return _clamp(_safe_float(assumptions["sprint_elapsed_pct"]), 0.0, 1.0), "assumption"


def _resolve_reference_timestamp(current_snapshot: dict[str, Any]) -> datetime:
    generated_at = _parse_optional_timestamp(current_snapshot.get("generated_at"))
    if generated_at is not None:
        return generated_at
    return datetime.now(timezone.utc)


def _parse_optional_timestamp(value: Any) -> datetime | None:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    if not normalized:
        return None
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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