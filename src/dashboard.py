from __future__ import annotations

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


def load_overview(api_base_url: str) -> tuple[dict[str, Any], str]:
    try:
        response = requests.get(f"{api_base_url}/overview", timeout=10)
        response.raise_for_status()
        return response.json(), "API + Postgres"
    except requests.RequestException:
        return build_tracking_overview(), "Direct AI_Tracking files"


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

    st.sidebar.caption(f"Tracking root: {settings.tracking_root}")
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
        st.dataframe(status_frame, use_container_width=True, hide_index=True)

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


def render_sprint_history(overview: dict[str, Any]) -> None:
    sprint_metrics = overview.get("sprint_metrics", [])
    if not sprint_metrics:
        st.info("No sprint metrics available.")
        return

    dataframe = pd.DataFrame(sprint_metrics)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], utc=True)
    chart_frame = dataframe[["timestamp", "remaining_story_points", "blocked_items"]]
    chart_frame = chart_frame.set_index("timestamp")

    st.subheader("Sprint Trajectory")
    st.write(
        "This live trend shows whether story points are burning down while blocker count is stable, rising, or stuck."
    )
    st.line_chart(chart_frame)
    st.dataframe(
        dataframe[["timestamp", "remaining_story_points", "blocked_items", "summary"]],
        use_container_width=True,
        hide_index=True,
    )


def render_usage_events(overview: dict[str, Any]) -> None:
    usage_events = overview.get("usage_events", [])
    if not usage_events:
        st.info("No usage events available.")
        return

    dataframe = pd.DataFrame(usage_events)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], utc=True)
    dataframe["actions_count"] = dataframe["actions"].apply(len)

    left_column, right_column = st.columns([1.2, 1])
    with left_column:
        st.subheader("Agent Usage Events")
        st.write(
            "Each row is a recorded agent work session with the scope summary and how many actions it produced."
        )
        st.dataframe(
            dataframe[
                [
                    "timestamp",
                    "title",
                    "remaining_story_points",
                    "blocked_items",
                    "actions_count",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
    with right_column:
        chart_frame = dataframe[["title", "actions_count"]].set_index("title")
        st.subheader("Actions Per Event")
        st.bar_chart(chart_frame)


def render_open_prs(overview: dict[str, Any]) -> None:
    current_snapshot = overview.get("current_snapshot", {})
    open_prs = current_snapshot.get("open_prs", [])
    if not open_prs:
        st.info("No open PRs found in the current snapshot.")
        return

    dataframe = pd.DataFrame(open_prs)
    st.subheader("Open Pull Requests")
    st.write(
        "PR age is a practical review-pressure signal because older PRs often correlate with blocked completion or delayed validation."
    )
    st.bar_chart(dataframe[["repository", "age_days"]].set_index("repository"))
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def render_daily_logs(overview: dict[str, Any]) -> None:
    st.subheader("Daily Action Logs")
    st.write(
        "Daily logs preserve the narrative trail behind the metrics, which is critical when auditing why the agent reported a given status."
    )
    for daily_log in overview.get("daily_logs", []):
        with st.expander(daily_log["name"]):
            st.markdown(daily_log["content"])


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

    sprint_tab, usage_tab, pr_tab, log_tab, developer_tab, leadership_tab = st.tabs(
        ["Sprint", "Agent Usage", "Pull Requests", "Daily Logs", "Developer", "Leadership"]
    )

    with sprint_tab:
        render_sprint_history(overview)
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
        {
            "value": [
                current["remaining_story_points"],
                current["remaining_work_hours"],
                current["assigned_items"],
                current["open_pr_count"],
                derived["recent_story_points_burn"],
            ]
        },
        index=[
            "Remaining SP",
            "Remaining hours",
            "Assigned items",
            "Open PRs",
            "Recent SP burn",
        ],
    )
    st.bar_chart(developer_frame)

    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row1_col1.metric("Review load per item", derived["review_load_per_item"])
    row1_col2.metric("Hours per item", derived["remaining_hours_per_item"])
    row1_col3.metric("SP per item", derived["story_points_per_item"])
    row1_col4.metric("Actions per session", derived["actions_per_session"])


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
        st.dataframe(support_frame, use_container_width=True, hide_index=True)


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
            st.dataframe(source_frame, use_container_width=True, hide_index=True)

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
        st.dataframe(
            pd.DataFrame(
                [
                    {"metric": key, "value": value}
                    for key, value in optimization_metrics.items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Story Point Impact Metrics")
        st.dataframe(
            pd.DataFrame(
                [
                    {"metric": key, "value": value}
                    for key, value in storypoint_metrics.items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    with debt_tab:
        preview_summary = repo_context.get("preview_summary", {})
        debt_summary = repo_context.get("technical_debt_summary", {})

        st.subheader("Technical Debt Cache")
        state_counts = debt_summary.get("state_counts", {})
        if state_counts:
            st.bar_chart(pd.DataFrame({"count": list(state_counts.values())}, index=list(state_counts.keys())))

        st.dataframe(
            pd.DataFrame(debt_summary.get("files", [])),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Technical Debt Preview Cache")
        st.dataframe(
            pd.DataFrame(preview_summary.get("files", [])),
            use_container_width=True,
            hide_index=True,
        )

    with audit_tab:
        st.subheader("MCP Audit Summary")
        st.dataframe(
            pd.DataFrame(
                [
                    {"metric": key, "value": value}
                    for key, value in audit_log.get("summary", {}).items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
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
        {
            "story_points": [
                tech_lead["planned_story_points"],
                tech_lead["expected_spent_story_points"],
                tech_lead["actual_spent_story_points"],
                manager["forecast_delivered_story_points"],
            ]
        },
        index=["Planned", "Expected spent", "Actual spent", "Forecast delivered"],
    )
    st.bar_chart(comparison_frame)

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

    st.info(
        "Expected burn is derived from a placeholder sprint elapsed percentage until live sprint start and end dates are exposed through AI_Tracking."
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

        manager_frame = pd.DataFrame(
            {
                "value": [
                    manager["remaining_story_points"],
                    manager["forecast_delivered_story_points"],
                    manager["scope_at_risk_story_points"],
                    manager["open_pr_count"],
                    manager["blocked_items"],
                ]
            },
            index=[
                "Remaining SP",
                "Forecast delivered SP",
                "Scope at risk SP",
                "Open PRs",
                "Blocked items",
            ],
        )
        st.bar_chart(manager_frame)

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
