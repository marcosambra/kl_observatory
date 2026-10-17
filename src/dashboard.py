from __future__ import annotations

import altair as alt
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, cast

import pandas as pd
import requests
import streamlit as st

from api.config import Settings, get_settings
from src.individual_metrics import build_individual_metrics
from src.leadership_metrics import build_leadership_metrics
from src.metric_plan import build_metric_implementation_plan
from api.services import build_tracking_overview
from src.mock_data import (
    build_metric_dictionary,
    build_mock_audit_signals,
    build_mock_leadership_assumptions,
)
from src.tracking_insights import build_tracking_insights


DashboardState = dict[str, Any]
SignalData = dict[str, Any]

SEMANTIC_COLORS = {
    "positive": "#22c55e",
    "negative": "#ef4444",
    "warning": "#fbbf24",
    "neutral": "#38bdf8",
    "accent": "#c084fc",
    "muted": "#94a3b8",
}

ROW_TONE_STYLES = {
    "positive": "background-color: rgba(34, 197, 94, 0.14); border-left: 0.35rem solid #22c55e;",
    "negative": "background-color: rgba(239, 68, 68, 0.14); border-left: 0.35rem solid #ef4444;",
    "warning": "background-color: rgba(251, 191, 36, 0.14); border-left: 0.35rem solid #fbbf24;",
    "neutral": "background-color: rgba(56, 189, 248, 0.12); border-left: 0.35rem solid #38bdf8;",
    "accent": "background-color: rgba(192, 132, 252, 0.14); border-left: 0.35rem solid #c084fc;",
    "muted": "background-color: rgba(148, 163, 184, 0.12); border-left: 0.35rem solid #94a3b8;",
}


def sync_via_api(api_base_url: str) -> tuple[bool, str]:
    try:
        response = requests.post(f"{api_base_url}/sync", timeout=10)
        response.raise_for_status()
        payload = response.json()
        return True, (
            "Synced "
            f"{payload['usage_events_synced']} usage events, "
            f"{payload['sprint_metrics_synced']} sprint rows, "
            f"{payload['snapshots_synced']} snapshots."
        )
    except requests.RequestException as exc:
        return False, str(exc)


def refresh_azure_via_api(api_base_url: str) -> tuple[bool, str]:
    try:
        response = requests.post(f"{api_base_url}/refresh/azure", timeout=180)
        response.raise_for_status()
        payload = response.json()
        sync_counts = (
            f"{payload['usage_events_synced']} usage events, "
            f"{payload['sprint_metrics_synced']} sprint rows, "
            f"{payload['snapshots_synced']} snapshots"
        )
        agent_stdout = payload.get("agent_refresh", {}).get("stdout", "")
        headline = agent_stdout.splitlines()[0] if agent_stdout else "Azure MCP refresh completed."
        return True, f"{headline} Persisted: {sync_counts}."
    except requests.RequestException as exc:
        return False, str(exc)


def load_overview(api_base_url: str) -> tuple[dict[str, Any], str]:
    try:
        response = requests.get(f"{api_base_url}/overview", timeout=10)
        response.raise_for_status()
        return response.json(), "API + Postgres"
    except requests.RequestException as error:
        return build_tracking_overview(), f"API unavailable ({type(error).__name__}); direct AI_Tracking files"


def format_timestamp(value: str | None) -> str:
    if not value:
        return "n/a"

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def load_dashboard_state() -> DashboardState:
    settings = get_settings()
    overview, source_label = load_overview(settings.api_base_url)
    individual_metrics = build_individual_metrics(overview)
    leadership_metrics = build_leadership_metrics(
        overview,
        build_mock_leadership_assumptions(),
    )
    metric_plan = build_metric_implementation_plan(
        overview.get("tracking_status", {}),
    )
    tracking_insights = build_tracking_insights(overview)
    return {
        "settings": settings,
        "overview": overview,
        "source_label": source_label,
        "persisted": overview.get("persisted"),
        "individual_metrics": individual_metrics,
        "leadership_metrics": leadership_metrics,
        "metric_plan": metric_plan,
        "tracking_insights": tracking_insights,
        "mock_signals": build_mock_audit_signals(),
        "metric_dictionary": build_metric_dictionary(),
    }


def get_dashboard_state() -> DashboardState:
    return cast(DashboardState, st.session_state["dashboard_state"])


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "kl_observatory_resources"

    return Path(__file__).resolve().parents[1]


def _logo_path() -> Path:
    return _resource_root() / "assets" / "ambra.png"


def _tone_for_label(label: str) -> str:
    normalized = label.strip().lower()
    if any(token in normalized for token in ("blocked", "error", "risk", "debt", "failed", "late", "stale")):
        return "negative"
    if any(token in normalized for token in ("done", "closed", "complete", "completed", "resolved", "success")):
        return "positive"
    if any(token in normalized for token in ("q.a", "qa", "review", "waiting", "pending", "warning", "validation")):
        return "warning"
    return "neutral"


def _tone_for_pr_age(age_days: Any) -> str:
    value = _safe_float(age_days)
    if value > 30:
        return "negative"
    if value > 7:
        return "warning"
    return "positive"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_semantic_frame(
    mapping: dict[str, Any],
    *,
    label_column: str,
    value_column: str,
) -> pd.DataFrame:
    if not mapping:
        return pd.DataFrame(columns=[label_column, value_column, "tone"])

    rows = [
        {
            label_column: label,
            value_column: _safe_float(value),
            "tone": _tone_for_label(str(label)),
        }
        for label, value in mapping.items()
    ]
    return pd.DataFrame(rows)


def render_semantic_bar_chart(
    dataframe: pd.DataFrame,
    *,
    label_column: str,
    value_column: str,
    height: int | None = None,
) -> None:
    if dataframe.empty:
        st.info("No chart data available.")
        return

    frame = dataframe.copy()
    if "tone" not in frame:
        frame["tone"] = "neutral"

    chart_height = height or max(220, len(frame) * 40)
    palette_domain = list(SEMANTIC_COLORS.keys())
    palette_range = [SEMANTIC_COLORS[key] for key in palette_domain]

    chart = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8)
        .encode(
            y=alt.Y(f"{label_column}:N", sort="-x", title=None),
            x=alt.X(f"{value_column}:Q", title=None),
            color=alt.Color(
                "tone:N",
                scale=alt.Scale(domain=palette_domain, range=palette_range),
                legend=None,
            ),
            tooltip=[label_column, value_column, "tone"],
        )
        .properties(height=chart_height)
    )
    st.altair_chart(chart, use_container_width=True)


def render_styled_dataframe(
    dataframe: pd.DataFrame,
    *,
    tone_resolver: Any,
) -> None:
    if dataframe.empty:
        st.info("No table data available.")
        return

    def style_row(row: pd.Series) -> list[str]:
        tone = str(tone_resolver(row) or "neutral")
        style = ROW_TONE_STYLES.get(tone, ROW_TONE_STYLES["neutral"])
        return [style] * len(row)

    styled = dataframe.style.apply(style_row, axis=1)
    try:
        styled = styled.hide(axis="index")
    except Exception:
        pass
    st.dataframe(styled, use_container_width=True)


def _tracking_row_tone(row: pd.Series) -> str:
    state = str(row.get("exists", "")).strip().lower()
    if state in {"missing", "false"}:
        return "negative"
    if state == "derived":
        return "warning"
    if state in {"present", "true"}:
        return "positive"
    return "neutral"


def _sprint_metric_row_tone(row: pd.Series) -> str:
    if _safe_float(row.get("blocked_items", 0)) > 0:
        return "negative"
    if _safe_float(row.get("remaining_story_points", 0)) <= 0:
        return "positive"
    return "warning"


def _usage_event_row_tone(row: pd.Series) -> str:
    if _safe_float(row.get("blocked_items", 0)) > 0:
        return "negative"
    if str(row.get("runtime_final_status", "")).strip().lower() in {"failed", "preview_failed", "execute_failed", "invalid_transition"}:
        return "negative"
    if _safe_float(row.get("actions_count", 0)) >= 3:
        return "positive"
    if str(row.get("runtime_flow_name", "")).strip():
        return "warning"
    return "neutral"


def _open_pr_row_tone(row: pd.Series) -> str:
    return _tone_for_pr_age(row.get("age_days", 0))


def render_page_header(title: str, description: str) -> None:
    logo_column, copy_column = st.columns([0.22, 0.78], vertical_alignment="center")

    with logo_column:
        logo_path = _logo_path()
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)

    with copy_column:
        st.title(title)
        st.write(description)


def render_sidebar_branding() -> None:
    logo_path = _logo_path()
    branding = st.sidebar.container()

    if logo_path.exists():
        branding.image(str(logo_path), use_container_width=True)

    branding.caption("Ambra for KwikLedgers")
    branding.divider()


def render_shell(state: DashboardState) -> None:
    settings = cast(Settings, state["settings"])
    overview = cast(dict[str, Any], state["overview"])
    persisted = cast(dict[str, Any] | None, state.get("persisted"))

    render_sidebar_branding()

    st.sidebar.title("KL Observatory")
    st.sidebar.write(
        "Native Streamlit observability for live tracking signals and planned audit telemetry."
    )

    if st.sidebar.button("Sync From AI_Tracking", use_container_width=True):
        synced, message = sync_via_api(settings.api_base_url)
        if synced:
            st.sidebar.success(message)
            st.rerun()
        else:
            st.sidebar.warning(f"API sync unavailable. {message}")

    if st.sidebar.button("Refresh From Azure Agent", use_container_width=True):
        refreshed, message = refresh_azure_via_api(settings.api_base_url)
        if refreshed:
            st.sidebar.success(message)
            st.rerun()
        else:
            st.sidebar.warning(f"Azure agent refresh unavailable. {message}")

    st.sidebar.caption(f"Tracking root: {settings.tracking_root}")
    st.sidebar.caption(f"Workspace root: {settings.workspace_root}")
    st.sidebar.caption(f"API: {settings.api_base_url}")
    st.sidebar.caption(f"Data source: {state['source_label']}")

    if persisted:
        st.sidebar.info(
            "Persisted rows: "
            f"{persisted['usage_events_synced']} usage events, "
            f"{persisted['sprint_metrics_synced']} sprint rows, "
            f"{persisted['snapshots_synced']} snapshots."
        )

    if not overview.get("tracking_status", {}).get("available", True):
        st.sidebar.warning(
            "Some AI_Tracking inputs are missing. Overview data may be partial."
        )

    st.sidebar.info(
        "Audit telemetry on the Audit Signals page is mocked in this first iteration so the observatory can already explain what must be measured next."
    )


def render_tracking_status(overview: dict[str, Any]) -> None:
    tracking_status = overview.get("tracking_status", {})
    if not tracking_status:
        return

    st.subheader("Tracking Status")
    st.write(
        "This checks whether the observatory can see each required AI_Tracking input before it renders sprint or usage views."
    )
    st.caption(f"Effective tracking root: {tracking_status.get('root', 'n/a')}")

    entries = tracking_status.get("entries", [])
    if entries:
        status_frame = pd.DataFrame(entries)
        if "state" in status_frame:
            status_frame["exists"] = status_frame["state"]
            status_frame = status_frame.drop(columns=["state"])
        else:
            status_frame["exists"] = status_frame["exists"].map(
                lambda value: "present" if value else "missing"
            )
        render_styled_dataframe(
            status_frame,
            tone_resolver=_tracking_row_tone,
        )

    current_snapshot = overview.get("current_snapshot", {})
    if current_snapshot.get("snapshot_source") == "derived_from_metrics":
        st.info(
            "`current-sprint.json` is missing, so the observatory is using a derived sprint snapshot reconstructed from `sprint-metrics.md` and `ai-usage-log.md`."
        )

    missing_paths = tracking_status.get("missing_paths", [])
    if not missing_paths:
        return

    missing_list = "\n".join(f"- {path}" for path in missing_paths)
    st.warning(
        "Some AI_Tracking inputs are missing. The observatory will show partial or empty data until the bind mount points at a populated tracking directory.\n\n"
        f"Tracking root: {tracking_status.get('root', 'n/a')}\n\n"
        f"Missing paths:\n{missing_list}"
    )
def render_metrics(
    overview: dict[str, Any],
    individual_metrics: dict[str, Any],
    leadership_metrics: dict[str, Any],
    tracking_insights: dict[str, Any],
) -> None:
    current_snapshot = overview.get("current_snapshot", {})
    counts = current_snapshot.get("counts", {})
    usage_events = overview.get("usage_events", [])
    actions_logged = sum(len(event.get("actions", [])) for event in usage_events)
    individual_current = individual_metrics["current"]
    individual_derived = individual_metrics["derived"]
    tech_lead = leadership_metrics["tech_lead"]
    manager = leadership_metrics["manager"]
    assumptions = leadership_metrics["assumptions"]
    insight_headline = tracking_insights["headline"]

    st.subheader("Operational Snapshot")
    st.write(
        "These live metrics summarize the current sprint load, delivery pressure, and recent agent activity already captured in AI_Tracking."
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Usage events", len(usage_events))
    col2.metric("Logged actions", actions_logged)
    col3.metric("Open PRs", counts.get("open_prs", 0))
    col4.metric(
        "Remaining story points",
        current_snapshot.get("remaining_story_points", 0),
    )

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Assigned items", counts.get("assigned_items", 0))
    col6.metric("Blocked items", counts.get("blocked_items", 0))
    col7.metric("User stories", counts.get("user_stories", 0))
    col8.metric(
        "Snapshot generated",
        format_timestamp(current_snapshot.get("generated_at")),
    )

    col9, col10, col11, col12 = st.columns(4)
    col9.metric("Planned SP", tech_lead["planned_story_points"])
    col10.metric(
        "Spent SP",
        tech_lead["actual_spent_story_points"],
        delta=f"{tech_lead['burn_variance_story_points']:+.1f} vs expected",
    )
    col11.metric(
        "Expected SP spent",
        tech_lead["expected_spent_story_points"],
        delta=f"{assumptions['sprint_elapsed_pct'] * 100:.0f}% sprint elapsed",
    )
    col12.metric(
        "Delivery confidence",
        f"{manager['delivery_confidence_pct']:.1f}%",
        delta=f"Forecast {manager['forecast_delivered_story_points']:.1f} SP",
    )

    col13, col14, col15, col16 = st.columns(4)
    col13.metric("Remaining work hours", individual_current["remaining_work_hours"])
    col14.metric(
        "Hours per item",
        individual_derived["remaining_hours_per_item"],
        delta=f"{individual_current['assigned_items']} assigned",
    )
    col15.metric(
        "Blocker pressure",
        f"{individual_derived['blocker_pressure_pct']:.1f}%",
        delta=f"{individual_current['blocked_items']} blocked",
    )
    col16.metric(
        "Recent SP burn",
        individual_derived["recent_story_points_burn"],
        delta=f"{individual_derived['blocker_delta']:+d} blocker delta",
    )

    col17, col18, col19, col20 = st.columns(4)
    col17.metric("Hours saved/mo", insight_headline["hours_saved_per_month"])
    col18.metric("AI impact index", f"{insight_headline['impact_index_pct']:.2f}%")
    col19.metric("Debt items tracked", insight_headline["technical_debt_items"])
    col20.metric("MCP audit errors", insight_headline["audit_errors"])

    col21, col22, col23, col24 = st.columns(4)
    col21.metric(
        "Tasks tracked",
        individual_current["tasks_all_statuses"],
        delta=f"{individual_current['sprint_stories']} sprint stories",
    )
    col22.metric(
        "Child items tracked",
        individual_current["children_of_assigned_items"],
        delta=f"{individual_current['blocked_children_of_assigned_items']:+d} blocked children",
        delta_color="inverse",
    )
    col23.metric(
        "Child blocker pressure",
        f"{individual_derived['child_blocker_pressure_pct']:.1f}%",
        delta=f"{individual_derived['open_children']} open children",
        delta_color="inverse",
    )
    col24.metric(
        "Sprint progress",
        f"{manager['progress_by_story_count_pct']:.1f}%",
        delta=f"{manager['progress_by_story_points_pct']:.1f}% by SP",
    )

    col25, col26 = st.columns(2)
    col25.metric("LangGraph runtime events", insight_headline.get("runtime_usage_events", 0))
    runtime_status_counts = tracking_insights.get("runtime_usage", {}).get("status_counts", {})
    col26.metric(
        "Runtime failure-like events",
        runtime_status_counts.get("failed", 0)
        + runtime_status_counts.get("preview_failed", 0)
        + runtime_status_counts.get("execute_failed", 0)
        + runtime_status_counts.get("invalid_transition", 0),
    )
    workflow_results = tracking_insights.get("workflow_results", {"source": "unavailable"})
    st.caption(f"Workflow evidence source: {workflow_results['source']}. "
               "Observed runs only; no coverage percentage or task-hours estimate.")
    if workflow_results["source"] in {"real", "partial"}:
        st.json(workflow_results)
    if workflow_results.get("errors"):
        st.warning("; ".join(workflow_results["errors"]))


def render_sprint_history(overview: dict[str, Any]) -> None:
    sprint_metrics = overview.get("sprint_metrics", [])
    if not sprint_metrics:
        st.info("No sprint metrics available.")
        return

    dataframe = pd.DataFrame(sprint_metrics)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], utc=True)
    chart_frame = dataframe[["timestamp", "remaining_story_points", "blocked_items"]].melt(
        id_vars="timestamp",
        var_name="series",
        value_name="value",
    )
    chart_frame["series"] = chart_frame["series"].map(
        {
            "remaining_story_points": "Remaining story points",
            "blocked_items": "Blocked items",
        }
    )

    st.subheader("Sprint Trajectory")
    st.write(
        "This live trend shows whether story points are burning down while blocker count is stable, rising, or stuck."
    )
    chart = (
        alt.Chart(chart_frame)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("timestamp:T", title=None),
            y=alt.Y("value:Q", title=None),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(
                    domain=["Remaining story points", "Blocked items"],
                    range=[SEMANTIC_COLORS["warning"], SEMANTIC_COLORS["negative"]],
                ),
                legend=alt.Legend(title=None),
            ),
            tooltip=["timestamp:T", "series:N", "value:Q"],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)
    render_styled_dataframe(
        dataframe[["timestamp", "remaining_story_points", "blocked_items", "summary"]],
        tone_resolver=_sprint_metric_row_tone,
    )


def render_usage_events(overview: dict[str, Any]) -> None:
    usage_events = overview.get("usage_events", [])
    if not usage_events:
        st.info("No usage events available.")
        return

    dataframe = pd.DataFrame(usage_events)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], utc=True)
    dataframe["actions_count"] = dataframe["actions"].apply(len)
    if "runtime_flow_name" not in dataframe:
        dataframe["runtime_flow_name"] = ""
    if "runtime_final_status" not in dataframe:
        dataframe["runtime_final_status"] = ""

    left_column, right_column = st.columns([1.2, 1])
    with left_column:
        st.subheader("Agent Usage Events")
        st.write(
            "Each row is a recorded agent work session with the scope summary and how many actions it produced."
        )
        render_styled_dataframe(
            dataframe[
                [
                    "timestamp",
                    "title",
                    "runtime_flow_name",
                    "runtime_final_status",
                    "remaining_story_points",
                    "blocked_items",
                    "actions_count",
                ]
            ],
            tone_resolver=_usage_event_row_tone,
        )
    with right_column:
        runtime_frame = dataframe[dataframe["runtime_flow_name"].astype(str).str.len() > 0].copy()
        if runtime_frame.empty:
            chart_frame = dataframe[["title", "actions_count"]].copy()
            chart_frame["tone"] = chart_frame["actions_count"].apply(
                lambda value: "positive" if value >= 3 else ("warning" if value == 2 else "neutral")
            )
            st.subheader("Actions Per Event")
            render_semantic_bar_chart(
                chart_frame,
                label_column="title",
                value_column="actions_count",
                height=260,
            )
        else:
            flow_counts = (
                runtime_frame.groupby("runtime_flow_name")
                .size()
                .reset_index(name="events")
            )
            flow_counts["tone"] = "warning"
            st.subheader("Runtime Events By Flow")
            render_semantic_bar_chart(
                flow_counts,
                label_column="runtime_flow_name",
                value_column="events",
                height=260,
            )

    runtime_frame = dataframe[dataframe["runtime_flow_name"].astype(str).str.len() > 0].copy()
    if not runtime_frame.empty:
        flow_column, status_column = st.columns(2)
        with flow_column:
            st.subheader("Runtime Final Status")
            status_counts = (
                runtime_frame.groupby("runtime_final_status")
                .size()
                .reset_index(name="events")
            )
            status_counts["tone"] = status_counts["runtime_final_status"].apply(
                lambda value: "negative"
                if str(value).strip().lower() in {"failed", "preview_failed", "execute_failed", "invalid_transition"}
                else ("positive" if str(value).strip().lower() == "completed" else "warning")
            )
            render_semantic_bar_chart(
                status_counts,
                label_column="runtime_final_status",
                value_column="events",
                height=240,
            )
        with status_column:
            st.subheader("Recent Runtime Executions")
            recent_runtime_frame = runtime_frame[
                [
                    "timestamp",
                    "runtime_flow_name",
                    "runtime_final_status",
                    "runtime_source",
                    "runtime_run_id",
                ]
            ].sort_values("timestamp", ascending=False)
            render_styled_dataframe(
                recent_runtime_frame.head(8),
                tone_resolver=_usage_event_row_tone,
            )


def render_open_prs(overview: dict[str, Any]) -> None:
    current_snapshot = overview.get("current_snapshot", {})
    open_prs = current_snapshot.get("open_prs", [])
    if not open_prs:
        st.info("No open PRs found in the current snapshot.")
        return

    dataframe = pd.DataFrame(open_prs)
    dataframe["tone"] = dataframe["age_days"].apply(_tone_for_pr_age)
    st.subheader("Open Pull Requests")
    st.write(
        "PR age is a practical review-pressure signal because older PRs often correlate with blocked completion or delayed validation."
    )
    render_semantic_bar_chart(
        dataframe[["repository", "age_days", "tone"]],
        label_column="repository",
        value_column="age_days",
        height=320,
    )
    render_styled_dataframe(dataframe, tone_resolver=_open_pr_row_tone)


def render_daily_logs(overview: dict[str, Any]) -> None:
    st.subheader("Daily Action Logs")
    st.write(
        "Daily logs preserve the narrative trail behind the metrics, which is critical when auditing why the agent reported a given status."
    )
    for daily_log in overview.get("daily_logs", []):
        with st.expander(daily_log["name"]):
            st.markdown(daily_log["content"])


def render_status_metrics_page(
    overview: dict[str, Any],
    individual_metrics: dict[str, Any],
    leadership_metrics: dict[str, Any],
) -> None:
    current_snapshot = overview.get("current_snapshot", {})
    counts = current_snapshot.get("counts", {})
    project_progress = current_snapshot.get("project_progress", {})
    child_summary = current_snapshot.get("child_items_summary", {})
    current = individual_metrics["current"]
    derived = individual_metrics["derived"]
    tech_lead = leadership_metrics["tech_lead"]
    manager = leadership_metrics["manager"]

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row1_col1.metric("Tasks all statuses", current["tasks_all_statuses"])
    row1_col2.metric("Children of assigned items", current["children_of_assigned_items"])
    row1_col3.metric(
        "Task completion",
        f"{derived['task_completion_pct']:.1f}%",
        delta=f"{derived['completed_tasks']} completed tasks",
    )
    row1_col4.metric(
        "Blocked story points",
        tech_lead["blocked_story_points"],
        delta=f"{tech_lead['blocked_stories']} blocked stories",
        delta_color="inverse",
    )

    task_states = counts.get("tasks_by_state", {}) if isinstance(counts.get("tasks_by_state", {}), dict) else {}
    assigned_types = counts.get("assigned_items_by_type", {}) if isinstance(counts.get("assigned_items_by_type", {}), dict) else {}
    story_states = project_progress.get("state_breakdown", {}) if isinstance(project_progress.get("state_breakdown", {}), dict) else {}

    left_column, right_column = st.columns(2)
    with left_column:
        st.subheader("Task Status Distribution")
        render_semantic_bar_chart(
            _build_semantic_frame(task_states, label_column="status", value_column="count"),
            label_column="status",
            value_column="count",
            height=280,
        )
    with right_column:
        st.subheader("Assigned Items By Type")
        render_semantic_bar_chart(
            _build_semantic_frame(assigned_types, label_column="type", value_column="count"),
            label_column="type",
            value_column="count",
            height=280,
        )

    left_column, right_column = st.columns(2)
    with left_column:
        st.subheader("Sprint Story States")
        render_semantic_bar_chart(
            _build_semantic_frame(story_states, label_column="state", value_column="count"),
            label_column="state",
            value_column="count",
            height=280,
        )
    with right_column:
        st.subheader("Child Item Execution")
        child_frame = pd.DataFrame(
            [
                {"signal": "Open children", "count": _safe_float(child_summary.get("open_children", 0)), "tone": "warning"},
                {"signal": "Completed children", "count": _safe_float(child_summary.get("completed_children", 0)), "tone": "positive"},
                {"signal": "Blocked children", "count": _safe_float(child_summary.get("blocked_children", 0)), "tone": "negative"},
                {"signal": "Parents with children", "count": _safe_float(child_summary.get("parents_with_children", 0)), "tone": "neutral"},
            ]
        )
        render_semantic_bar_chart(
            child_frame,
            label_column="signal",
            value_column="count",
            height=280,
        )

    st.subheader("Status Summary")
    summary_frame = pd.DataFrame(
        [
            {
                "metric": "Sprint progress by story count",
                "value": f"{manager['progress_by_story_count_pct']:.1f}%",
                "meaning": "Tracks how much of the sprint story inventory is complete.",
            },
            {
                "metric": "Sprint progress by story points",
                "value": f"{manager['progress_by_story_points_pct']:.1f}%",
                "meaning": "Shows delivery progress weighted by story points instead of item count.",
            },
            {
                "metric": "Child blocker pressure",
                "value": f"{derived['child_blocker_pressure_pct']:.1f}%",
                "meaning": "Measures whether execution risk is hiding under child items instead of top-level assignments.",
            },
            {
                "metric": "Sprint stories tracked",
                "value": current["sprint_stories"],
                "meaning": "Total stories visible in the current sprint snapshot, even when not assigned to the active developer.",
            },
        ]
    )
    render_styled_dataframe(summary_frame, tone_resolver=lambda row: _tone_for_label(str(row.get("metric", ""))))


def render_overview_page() -> None:
    state = get_dashboard_state()
    overview = cast(dict[str, Any], state["overview"])
    persisted = cast(dict[str, Any] | None, state.get("persisted"))
    individual_metrics = cast(dict[str, Any], state["individual_metrics"])
    leadership_metrics = cast(dict[str, Any], state["leadership_metrics"])
    tracking_insights = cast(dict[str, Any], state["tracking_insights"])

    render_page_header(
        "Operations Overview",
        "Observe live sprint movement, agent usage, PR pressure, and daily audit context without injecting HTML into Streamlit."
    )

    if persisted:
        st.caption(
            "Persisted rows available from the API cache: "
            f"{persisted['usage_events_synced']} usage events, "
            f"{persisted['sprint_metrics_synced']} sprint rows, "
            f"{persisted['snapshots_synced']} snapshots."
        )

    render_tracking_status(overview)
    render_metrics(overview, individual_metrics, leadership_metrics, tracking_insights)

    sprint_tab, status_tab, usage_tab, pr_tab, log_tab, developer_tab, leadership_tab = st.tabs(
        ["Sprint", "Status Map", "Agent Usage", "Pull Requests", "Daily Logs", "Developer", "Leadership"]
    )

    with sprint_tab:
        render_sprint_history(overview)
    with status_tab:
        render_status_metrics_page(overview, individual_metrics, leadership_metrics)
    with usage_tab:
        render_usage_events(overview)
    with pr_tab:
        render_open_prs(overview)
    with log_tab:
        render_daily_logs(overview)
    with developer_tab:
        render_individual_summary(individual_metrics)
    with leadership_tab:
        render_leadership_summary(leadership_metrics)


def render_individual_summary(individual_metrics: dict[str, Any]) -> None:
    current = individual_metrics["current"]
    derived = individual_metrics["derived"]

    st.subheader("Developer Snapshot")
    st.write(
        "These metrics stay focused on the active developer context saved in the current sprint snapshot and the AI usage log."
    )

    developer_frame = pd.DataFrame(
        [
            {"signal": "Remaining SP", "value": current["remaining_story_points"], "tone": "warning"},
            {"signal": "Remaining hours", "value": current["remaining_work_hours"], "tone": "warning"},
            {"signal": "Assigned items", "value": current["assigned_items"], "tone": "neutral"},
            {"signal": "Open PRs", "value": current["open_pr_count"], "tone": "warning"},
            {"signal": "Recent SP burn", "value": derived["recent_story_points_burn"], "tone": "positive"},
        ]
    )
    render_semantic_bar_chart(
        developer_frame,
        label_column="signal",
        value_column="value",
        height=260,
    )

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row1_col1.metric("Review load per item", derived["review_load_per_item"])
    row1_col2.metric("Hours per item", derived["remaining_hours_per_item"])
    row1_col3.metric("SP per item", derived["story_points_per_item"])
    row1_col4.metric("Actions per session", derived["actions_per_session"])

    task_states = current.get("tasks_by_state", {})
    if task_states:
        st.subheader("Task States For This Context")
        render_semantic_bar_chart(
            _build_semantic_frame(task_states, label_column="status", value_column="count"),
            label_column="status",
            value_column="count",
            height=240,
        )


def render_individual_page() -> None:
    state = get_dashboard_state()
    individual_metrics = cast(dict[str, Any], state["individual_metrics"])
    current = individual_metrics["current"]
    derived = individual_metrics["derived"]

    render_page_header(
        "Individual Metrics",
        "Developer-facing metrics for the active user saved in the current sprint snapshot and the AI tracking logs."
    )

    st.caption(f"Active developer: {individual_metrics['user_email']}")

    workload_tab, support_tab = st.tabs(["Workload", "Agent Support"])

    with workload_tab:
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("Assigned items", current["assigned_items"])
        row1_col2.metric("Blocked items", current["blocked_items"])
        row1_col3.metric("Remaining SP", current["remaining_story_points"])
        row1_col4.metric("Remaining work hours", current["remaining_work_hours"])

        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("Blocker pressure", f"{derived['blocker_pressure_pct']:.1f}%")
        row2_col2.metric("Review load per item", derived["review_load_per_item"])
        row2_col3.metric("Hours per item", derived["remaining_hours_per_item"])
        row2_col4.metric(
            "Recent SP burn",
            derived["recent_story_points_burn"],
            delta=f"{derived['blocker_delta']:+d} blocker delta",
        )

        row3_col1, row3_col2, row3_col3, row3_col4 = st.columns(4)
        row3_col1.metric("Tasks all statuses", current["tasks_all_statuses"])
        row3_col2.metric("Sprint stories", current["sprint_stories"])
        row3_col3.metric("Children tracked", current["children_of_assigned_items"])
        row3_col4.metric(
            "Child blocker pressure",
            f"{derived['child_blocker_pressure_pct']:.1f}%",
            delta=f"{current['blocked_children_of_assigned_items']:+d} blocked children",
            delta_color="inverse",
        )

        task_state_column, item_type_column = st.columns(2)
        with task_state_column:
            st.subheader("Task Status Breakdown")
            render_semantic_bar_chart(
                _build_semantic_frame(current["tasks_by_state"], label_column="status", value_column="count"),
                label_column="status",
                value_column="count",
                height=260,
            )
        with item_type_column:
            st.subheader("Assigned Item Types")
            render_semantic_bar_chart(
                _build_semantic_frame(current["assigned_items_by_type"], label_column="type", value_column="count"),
                label_column="type",
                value_column="count",
                height=260,
            )

    with support_tab:
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("Usage sessions", derived["usage_sessions"])
        row1_col2.metric("Logged actions", derived["actions_logged"])
        row1_col3.metric("Actions per session", derived["actions_per_session"])
        row1_col4.metric("Open PRs", current["open_pr_count"])

        support_frame = pd.DataFrame(
            [
                {
                    "signal": "Latest agent touchpoint",
                    "value": derived["latest_usage_timestamp"] or "n/a",
                    "meaning": "Most recent AI usage event captured in the operational log.",
                },
                {
                    "signal": "Latest agent activity",
                    "value": derived["latest_usage_title"],
                    "meaning": "Title of the last recorded AI support session for this workspace context.",
                },
            ]
        )
        render_styled_dataframe(support_frame, tone_resolver=lambda row: "neutral")


def render_metric_plan_page() -> None:
    state = get_dashboard_state()
    plan_rows = cast(list[dict[str, str]], state["metric_plan"])
    tracking_status = cast(dict[str, Any], state["overview"]).get("tracking_status", {})

    render_page_header(
        "Metric Implementation Plan",
        "Roadmap for expanding observatory metrics using the KwikLedgers agent contract and the files already saved under AI_Tracking."
    )

    st.write(
        "This plan is grounded in the contract sections that already require daily summaries, sprint control files, AI usage metrics, blocker detection, and narrative logs."
    )

    if tracking_status:
        source_frame = pd.DataFrame(tracking_status.get("entries", []))
        if not source_frame.empty:
            source_frame["exists"] = source_frame["exists"].map(
                lambda value: "present" if value else "missing"
            )
            st.subheader("Current Saved Sources")
            render_styled_dataframe(source_frame, tone_resolver=_tracking_row_tone)

    st.subheader("Implementation Roadmap")
    st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)


def render_tracking_artifacts_page() -> None:
    state = get_dashboard_state()
    overview = cast(dict[str, Any], state["overview"])
    insights = cast(dict[str, Any], state["tracking_insights"])
    optimization = overview.get("optimization_report", {})
    storypoints = overview.get("storypoints_report", {})
    repo_context = overview.get("repo_work_item_context", {})
    audit_log = overview.get("audit_log", {})
    current_sprint_markdown = overview.get("current_sprint_markdown", "")

    render_page_header(
        "AI_Tracking Knowledge",
        "Metrics and context parsed from the full AI_Tracking surface, including optimization reports, sprint-impact reports, debt caches, and MCP audit logs."
    )

    headline = insights["headline"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Hours saved/mo", headline["hours_saved_per_month"])
    col2.metric("Impact index", f"{headline['impact_index_pct']:.2f}%")
    col3.metric("Preview cache entries", headline["preview_entries"])
    col4.metric("Audit errors", headline["audit_errors"])

    reports_tab, debt_tab, audit_tab, snapshot_tab = st.tabs(
        ["Reports", "Debt Context", "Audit Log", "Task Control"]
    )

    with reports_tab:
        optimization_metrics = optimization.get("metrics", {})
        storypoint_metrics = storypoints.get("metrics", {})

        st.subheader("Optimization Report Metrics")
        render_styled_dataframe(
            pd.DataFrame(
                [
                    {"metric": key, "value": value}
                    for key, value in optimization_metrics.items()
                ]
            ),
            tone_resolver=lambda row: _tone_for_label(str(row.get("metric", ""))),
        )

        st.subheader("Story Point Impact Metrics")
        render_styled_dataframe(
            pd.DataFrame(
                [
                    {"metric": key, "value": value}
                    for key, value in storypoint_metrics.items()
                ]
            ),
            tone_resolver=lambda row: _tone_for_label(str(row.get("metric", ""))),
        )

    with debt_tab:
        preview_summary = repo_context.get("preview_summary", {})
        debt_summary = repo_context.get("technical_debt_summary", {})

        st.subheader("Technical Debt Cache")
        state_counts = debt_summary.get("state_counts", {})
        if state_counts:
            render_semantic_bar_chart(
                _build_semantic_frame(state_counts, label_column="state", value_column="count"),
                label_column="state",
                value_column="count",
                height=260,
            )

        render_styled_dataframe(
            pd.DataFrame(debt_summary.get("files", [])),
            tone_resolver=lambda row: _tone_for_label(str(row.get("state", row.get("repository_name", "")))),
        )

        st.subheader("Technical Debt Preview Cache")
        render_styled_dataframe(
            pd.DataFrame(preview_summary.get("files", [])),
            tone_resolver=lambda row: "neutral",
        )

    with audit_tab:
        st.subheader("MCP Audit Summary")
        render_styled_dataframe(
            pd.DataFrame(
                [
                    {"metric": key, "value": value}
                    for key, value in audit_log.get("summary", {}).items()
                ]
            ),
            tone_resolver=lambda row: _tone_for_label(str(row.get("metric", ""))),
        )

        tail_lines = audit_log.get("tail", [])
        if tail_lines:
            st.subheader("Recent Audit Entries")
            st.code("\n".join(tail_lines[-40:]), language="text")

    with snapshot_tab:
        if current_sprint_markdown:
            st.markdown(current_sprint_markdown)
        else:
            st.info("No current sprint markdown snapshot is available yet.")


def render_leadership_summary(leadership_metrics: dict[str, Any]) -> None:
    tech_lead = leadership_metrics["tech_lead"]
    manager = leadership_metrics["manager"]

    st.subheader("Leadership Snapshot")
    st.write(
        "These cards convert the sprint history into execution metrics that a tech lead or manager can act on quickly."
    )

    comparison_frame = pd.DataFrame(
        [
            {"signal": "Planned", "story_points": tech_lead["planned_story_points"], "tone": "neutral"},
            {"signal": "Expected spent", "story_points": tech_lead["expected_spent_story_points"], "tone": "warning"},
            {"signal": "Actual spent", "story_points": tech_lead["actual_spent_story_points"], "tone": "positive"},
            {"signal": "Forecast delivered", "story_points": manager["forecast_delivered_story_points"], "tone": "accent"},
        ]
    )
    render_semantic_bar_chart(
        comparison_frame,
        label_column="signal",
        value_column="story_points",
        height=240,
    )

    lead_col1, lead_col2, lead_col3, lead_col4 = st.columns(4)
    lead_col1.metric("Burn efficiency", f"{tech_lead['burn_efficiency_pct']:.1f}%")
    lead_col2.metric("Blocked scope", f"{tech_lead['blocked_scope_pct']:.1f}%")
    lead_col3.metric("Average PR age", f"{tech_lead['average_pr_age_days']:.1f} days")
    lead_col4.metric("Actions per event", tech_lead["actions_per_event"])

    manager_col1, manager_col2, manager_col3, manager_col4 = st.columns(4)
    manager_col1.metric("Completion", f"{manager['completion_pct']:.1f}%")
    manager_col2.metric("Expected completion", f"{manager['expected_completion_pct']:.1f}%")
    manager_col3.metric("Scope at risk", manager["scope_at_risk_story_points"])
    manager_col4.metric("Review pressure", f"{manager['review_pressure_pct']:.1f}%")

    lead_col5, lead_col6, lead_col7, lead_col8 = st.columns(4)
    lead_col5.metric("Blocked story points", tech_lead["blocked_story_points"])
    lead_col6.metric("Blocked stories", tech_lead["blocked_stories"])
    lead_col7.metric("Children tracked", tech_lead["children_of_assigned_items"])
    lead_col8.metric("Child blocker pressure", f"{tech_lead['child_blocker_pressure_pct']:.1f}%")

    manager_col5, manager_col6, manager_col7, manager_col8 = st.columns(4)
    manager_col5.metric("Progress by story count", f"{manager['progress_by_story_count_pct']:.1f}%")
    manager_col6.metric("Progress by story points", f"{manager['progress_by_story_points_pct']:.1f}%")
    manager_col7.metric("Completed children", manager["completed_children"])
    manager_col8.metric("Sprint stories", manager["sprint_stories"])


def render_leadership_page() -> None:
    state = get_dashboard_state()
    leadership_metrics = cast(dict[str, Any], state["leadership_metrics"])
    assumptions = leadership_metrics["assumptions"]
    tech_lead = leadership_metrics["tech_lead"]
    manager = leadership_metrics["manager"]

    render_page_header(
        "Leadership Metrics",
        "Numerical sprint KPIs for the tech lead and manager, including expected story-point burn versus actual burn."
    )

    if assumptions.get("elapsed_source") == "sprint_context":
        st.info(
            "Expected burn is calculated from the live sprint start and finish dates stored in `sprint_context`, using the snapshot generation time as the reference point."
        )
    else:
        st.info(
            "Expected burn is using the fallback sprint elapsed percentage because the current snapshot does not expose usable sprint dates yet."
        )

    tech_lead_tab, manager_tab, assumptions_tab = st.tabs(
        ["Tech Lead", "Manager", "Assumptions"]
    )

    with tech_lead_tab:
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("Planned SP", tech_lead["planned_story_points"])
        row1_col2.metric("Actual spent SP", tech_lead["actual_spent_story_points"])
        row1_col3.metric("Expected spent SP", tech_lead["expected_spent_story_points"])
        row1_col4.metric(
            "Burn variance",
            tech_lead["burn_variance_story_points"],
            delta=f"{tech_lead['burn_efficiency_pct']:.1f}% efficiency",
        )

        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("Blocked items", tech_lead["blocked_items"])
        row2_col2.metric("Blocked scope", f"{tech_lead['blocked_scope_pct']:.1f}%")
        row2_col3.metric("Average PR age", f"{tech_lead['average_pr_age_days']:.1f} days")
        row2_col4.metric("Actions per event", tech_lead["actions_per_event"])

        row3_col1, row3_col2, row3_col3, row3_col4 = st.columns(4)
        row3_col1.metric("Blocked story points", tech_lead["blocked_story_points"])
        row3_col2.metric("Blocked stories", tech_lead["blocked_stories"])
        row3_col3.metric("Children tracked", tech_lead["children_of_assigned_items"])
        row3_col4.metric("Child blocker pressure", f"{tech_lead['child_blocker_pressure_pct']:.1f}%")

    with manager_tab:
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("Completion", f"{manager['completion_pct']:.1f}%")
        row1_col2.metric("Expected completion", f"{manager['expected_completion_pct']:.1f}%")
        row1_col3.metric("Forecast delivered SP", manager["forecast_delivered_story_points"])
        row1_col4.metric("Delivery confidence", f"{manager['delivery_confidence_pct']:.1f}%")

        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("Remaining SP", manager["remaining_story_points"])
        row2_col2.metric("Scope at risk", manager["scope_at_risk_story_points"])
        row2_col3.metric("Review pressure", f"{manager['review_pressure_pct']:.1f}%")
        row2_col4.metric("Work in progress", manager["work_in_progress_items"])

        row3_col1, row3_col2, row3_col3, row3_col4 = st.columns(4)
        row3_col1.metric("Progress by story count", f"{manager['progress_by_story_count_pct']:.1f}%")
        row3_col2.metric("Progress by story points", f"{manager['progress_by_story_points_pct']:.1f}%")
        row3_col3.metric("Completed children", manager["completed_children"])
        row3_col4.metric("Blocked child items", manager["blocked_children_of_assigned_items"])

        manager_frame = pd.DataFrame(
            [
                {"signal": "Remaining SP", "value": manager["remaining_story_points"], "tone": "warning"},
                {"signal": "Forecast delivered SP", "value": manager["forecast_delivered_story_points"], "tone": "positive"},
                {"signal": "Scope at risk SP", "value": manager["scope_at_risk_story_points"], "tone": "negative"},
                {"signal": "Open PRs", "value": manager["open_pr_count"], "tone": "warning"},
                {"signal": "Blocked items", "value": manager["blocked_items"], "tone": "negative"},
            ]
        )
        render_semantic_bar_chart(
            manager_frame,
            label_column="signal",
            value_column="value",
            height=260,
        )

    with assumptions_tab:
        assumptions_frame = pd.DataFrame(
            [
                {
                    "assumption": "Sprint elapsed percentage",
                    "value": f"{assumptions['sprint_elapsed_pct'] * 100:.0f}%",
                    "meaning": "Used to estimate the expected story points that should have been spent by now.",
                },
                {
                    "assumption": "Target open PRs",
                    "value": assumptions["target_open_prs"],
                    "meaning": "Reference ceiling used to compute review-pressure percentage.",
                },
                {
                    "assumption": "PR review SLA",
                    "value": f"{assumptions['pr_review_sla_days']:.1f} days",
                    "meaning": "Review age beyond this point reduces delivery confidence.",
                },
            ]
        )
        st.dataframe(assumptions_frame, use_container_width=True, hide_index=True)


def render_mock_signal(signal: SignalData) -> None:
    dataframe = pd.DataFrame(signal["rows"])
    index_column = cast(str, signal["index_column"])
    chart_columns = cast(list[str], signal["chart_columns"])

    st.subheader(cast(str, signal["title"]))
    st.write(cast(str, signal["meaning"]))
    st.caption(f"Importance: {signal['importance']}")
    st.bar_chart(dataframe.set_index(index_column)[chart_columns])
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def render_audit_signals_page() -> None:
    state = get_dashboard_state()
    signals = cast(list[SignalData], state["mock_signals"])
    signal_lookup = {signal["key"]: signal for signal in signals}

    tool_frame = pd.DataFrame(signal_lookup["tool_reliability"]["rows"])
    guardrail_frame = pd.DataFrame(signal_lookup["approval_guardrails"]["rows"])
    freshness_frame = pd.DataFrame(signal_lookup["tracking_freshness"]["rows"])
    traceability_frame = pd.DataFrame(signal_lookup["traceability_coverage"]["rows"])

    render_page_header(
        "Audit Signals",
        "These datasets are mocked in the first iteration. They define the telemetry the KwikLedgers dev agent should emit next so audits can cover health, governance, and traceability."
    )

    st.info(
        "These datasets are mocked in the first iteration. They define the telemetry the KwikLedgers dev agent should emit next so audits can cover health, governance, and traceability."
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Average tool success", f"{tool_frame['success_rate_pct'].mean():.1f}%")
    col2.metric(
        "Blocked writes without approval",
        int(guardrail_frame["blocked_without_approval"].sum()),
    )
    col3.metric(
        "Artifacts outside target lag",
        int(
            (
                freshness_frame["lag_minutes"]
                > freshness_frame["target_lag_minutes"]
            ).sum()
        ),
    )
    col4.metric(
        "Average traceability coverage",
        f"{traceability_frame['coverage_pct'].mean():.1f}%",
    )

    for signal in signals:
        render_mock_signal(signal)


def render_dictionary_page() -> None:
    state = get_dashboard_state()
    dictionary = pd.DataFrame(state["metric_dictionary"])

    render_page_header(
        "Metric Dictionary",
        "This page explains what each live metric or mocked audit signal means and why it matters when auditing the MCP stack and the dev agent behavior."
    )

    for group in dictionary["group"].drop_duplicates():
        st.subheader(group)
        group_entries = dictionary[dictionary["group"] == group].to_dict("records")
        for entry in group_entries:
            with st.expander(f"{entry['name']} [{entry['status']}]"):
                st.write(f"Meaning: {entry['meaning']}")
                st.write(f"Importance: {entry['importance']}")


def main() -> None:
    st.set_page_config(
        page_title="KL Agent Observatory",
        page_icon=":material/monitoring:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    state = load_dashboard_state()
    st.session_state["dashboard_state"] = state
    render_shell(state)

    navigation = st.navigation(
        [
            st.Page(
                render_overview_page,
                title="Operations Overview",
                icon=":material/dashboard:",
            ),
            st.Page(
                render_leadership_page,
                title="Leadership Metrics",
                icon=":material/insights:",
            ),
            st.Page(
                render_individual_page,
                title="Individual Metrics",
                icon=":material/person:",
            ),
            st.Page(
                render_audit_signals_page,
                title="Audit Signals",
                icon=":material/gavel:",
            ),
            st.Page(
                render_tracking_artifacts_page,
                title="AI_Tracking Knowledge",
                icon=":material/hub:",
            ),
            st.Page(
                render_metric_plan_page,
                title="Metric Implementation Plan",
                icon=":material/schema:",
            ),
            st.Page(
                render_dictionary_page,
                title="Metric Dictionary",
                icon=":material/menu_book:",
            ),
        ]
    )
    navigation.run()


if __name__ == "__main__":
    main()
