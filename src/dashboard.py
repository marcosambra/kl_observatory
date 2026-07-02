from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from api.config import get_settings
from api.services import build_tracking_overview


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(15, 118, 110, 0.12), transparent 30%),
                linear-gradient(180deg, #f7f1e8 0%, #fcfaf5 100%);
        }
        div[data-testid="metric-container"] {
            background: rgba(255, 252, 247, 0.9);
            border: 1px solid rgba(31, 41, 51, 0.08);
            border-radius: 16px;
            padding: 1rem;
            box-shadow: 0 12px 30px rgba(31, 41, 51, 0.06);
        }
        .hero {
            padding: 1.25rem 1.5rem;
            border: 1px solid rgba(31, 41, 51, 0.08);
            border-radius: 20px;
            background: rgba(255, 250, 241, 0.88);
            box-shadow: 0 18px 42px rgba(31, 41, 51, 0.08);
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def load_overview(api_base_url: str) -> tuple[dict, str]:
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


def render_tracking_status(overview: dict) -> None:
    tracking_status = overview.get("tracking_status", {})
    if not tracking_status:
        return

    st.subheader("Tracking Status")
    st.caption(f"Effective tracking root: {tracking_status.get('root', 'n/a')}")

    entries = tracking_status.get("entries", [])
    if entries:
        status_frame = pd.DataFrame(entries)
        status_frame["exists"] = status_frame["exists"].map(
            lambda value: "present" if value else "missing"
        )
        st.dataframe(status_frame, use_container_width=True, hide_index=True)

    missing_paths = tracking_status.get("missing_paths", [])
    if not missing_paths:
        return

    missing_list = "\n".join(f"- {path}" for path in missing_paths)
    st.warning(
        "Some AI_Tracking inputs are missing. The observatory will show partial or empty data until the bind mount points at a populated tracking directory.\n\n"
        f"Tracking root: {tracking_status.get('root', 'n/a')}\n\n"
        f"Missing paths:\n{missing_list}"
    )


def render_metrics(overview: dict) -> None:
    current_snapshot = overview.get("current_snapshot", {})
    counts = current_snapshot.get("counts", {})
    usage_events = overview.get("usage_events", [])
    actions_logged = sum(len(event.get("actions", [])) for event in usage_events)

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


def render_sprint_history(overview: dict) -> None:
    sprint_metrics = overview.get("sprint_metrics", [])
    if not sprint_metrics:
        st.info("No sprint metrics available.")
        return

    dataframe = pd.DataFrame(sprint_metrics)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], utc=True)
    chart_frame = dataframe[["timestamp", "remaining_story_points", "blocked_items"]]
    chart_frame = chart_frame.set_index("timestamp")

    st.subheader("Sprint Trajectory")
    st.line_chart(chart_frame)
    st.dataframe(
        dataframe[["timestamp", "remaining_story_points", "blocked_items", "summary"]],
        use_container_width=True,
        hide_index=True,
    )


def render_usage_events(overview: dict) -> None:
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
        st.dataframe(
            dataframe[[
                "timestamp",
                "title",
                "remaining_story_points",
                "blocked_items",
                "actions_count",
            ]],
            use_container_width=True,
            hide_index=True,
        )
    with right_column:
        chart_frame = dataframe[["title", "actions_count"]].set_index("title")
        st.subheader("Actions Per Event")
        st.bar_chart(chart_frame)


def render_open_prs(overview: dict) -> None:
    current_snapshot = overview.get("current_snapshot", {})
    open_prs = current_snapshot.get("open_prs", [])
    if not open_prs:
        st.info("No open PRs found in the current snapshot.")
        return

    dataframe = pd.DataFrame(open_prs)
    st.subheader("Open Pull Requests")
    st.bar_chart(dataframe[["repository", "age_days"]].set_index("repository"))
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def render_daily_logs(overview: dict) -> None:
    st.subheader("Daily Action Logs")
    for daily_log in overview.get("daily_logs", []):
        with st.expander(daily_log["name"]):
            st.markdown(daily_log["content"])


def main() -> None:
    settings = get_settings()

    st.set_page_config(
        page_title=settings.app_name,
        page_icon="observatory",
        layout="wide",
    )
    inject_styles()

    st.markdown(
        """
        <div class="hero">
            <h1>KL Observatory</h1>
            <p>Streamlit observability for agent usage, sprint movement, PR pressure, and daily operational logs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_column, info_column = st.columns([0.3, 0.7])
    with action_column:
        if st.button("Sync From AI_Tracking", use_container_width=True):
            synced, message = sync_via_api(settings.api_base_url)
            if synced:
                st.success(message)
            else:
                st.warning(f"API sync unavailable. {message}")
    with info_column:
        st.caption(
            f"Tracking root: {settings.tracking_root} | API: {settings.api_base_url}"
        )

    overview, source_label = load_overview(settings.api_base_url)
    persisted = overview.get("persisted")

    st.caption(f"Data source: {source_label}")
    if persisted:
        st.caption(
            "Persisted rows: "
            f"{persisted['usage_events_synced']} usage events, "
            f"{persisted['sprint_metrics_synced']} sprint rows, "
            f"{persisted['snapshots_synced']} snapshots."
        )

    render_tracking_status(overview)
    render_metrics(overview)
    render_sprint_history(overview)
    render_usage_events(overview)
    render_open_prs(overview)
    render_daily_logs(overview)


if __name__ == "__main__":
    main()
