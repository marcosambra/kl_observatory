from __future__ import annotations


def build_mock_leadership_assumptions() -> dict[str, float]:
    return {
        "sprint_elapsed_pct": 0.65,
        "target_open_prs": 4.0,
        "pr_review_sla_days": 2.0,
    }


def build_mock_audit_signals() -> list[dict[str, object]]:
    return [
        {
            "key": "tool_reliability",
            "title": "MCP Tool Reliability",
            "meaning": (
                "Shows how often each MCP surface completes successfully and how much "
                "latency the agent sees before it can continue reasoning."
            ),
            "importance": (
                "Reliability and tail latency are the fastest signals that the agent may "
                "be making decisions on stale, partial, or delayed context."
            ),
            "index_column": "surface",
            "chart_columns": ["success_rate_pct", "p95_latency_seconds"],
            "rows": [
                {
                    "surface": "Azure daily summary",
                    "server": "kwikledgers-azure-devops",
                    "calls": 124,
                    "success_rate_pct": 97.6,
                    "p95_latency_seconds": 2.4,
                    "incident_note": "One retry spike after team-context recovery.",
                },
                {
                    "surface": "Local tracking sync",
                    "server": "kwikledgers-local-tracking",
                    "calls": 91,
                    "success_rate_pct": 99.1,
                    "p95_latency_seconds": 0.8,
                    "incident_note": "One empty bind mount produced partial data warnings.",
                },
                {
                    "surface": "Windows reminders",
                    "server": "kwikledgers-windows",
                    "calls": 18,
                    "success_rate_pct": 88.9,
                    "p95_latency_seconds": 1.7,
                    "incident_note": "WSL notification bridge unavailable on one run.",
                },
            ],
        },
        {
            "key": "approval_guardrails",
            "title": "Approval Guardrail Coverage",
            "meaning": (
                "Tracks whether Azure DevOps writes were previewed, explicitly approved, "
                "or blocked before any mutation could happen."
            ),
            "importance": (
                "This is the clearest governance signal for the dev agent because it proves "
                "that write actions stay auditable and under human approval."
            ),
            "index_column": "operation_type",
            "chart_columns": [
                "previews_presented",
                "approved_writes",
                "blocked_without_approval",
            ],
            "rows": [
                {
                    "operation_type": "Technical debt creation",
                    "previews_presented": 6,
                    "approved_writes": 6,
                    "blocked_without_approval": 1,
                    "notes": "One attempt stopped after preview because parent link was missing.",
                },
                {
                    "operation_type": "Work item effort update",
                    "previews_presented": 4,
                    "approved_writes": 4,
                    "blocked_without_approval": 0,
                    "notes": "All updates had explicit confirmation in chat.",
                },
                {
                    "operation_type": "Sprint reassignment",
                    "previews_presented": 2,
                    "approved_writes": 1,
                    "blocked_without_approval": 1,
                    "notes": "One change was held because the destination sprint was ambiguous.",
                },
            ],
        },
        {
            "key": "tracking_freshness",
            "title": "Tracking Freshness",
            "meaning": (
                "Measures how far each required tracking artifact is from its expected update "
                "cadence before the observatory reads it."
            ),
            "importance": (
                "Freshness protects the agent from presenting old sprint state or outdated PR "
                "pressure as if it were current."
            ),
            "index_column": "artifact",
            "chart_columns": ["lag_minutes", "target_lag_minutes"],
            "rows": [
                {
                    "artifact": "current-sprint.json",
                    "owner": "Task control sync",
                    "lag_minutes": 22,
                    "target_lag_minutes": 60,
                    "status": "healthy",
                },
                {
                    "artifact": "ai-usage-log.md",
                    "owner": "AI usage metrics",
                    "lag_minutes": 14,
                    "target_lag_minutes": 30,
                    "status": "healthy",
                },
                {
                    "artifact": "sprint-metrics.md",
                    "owner": "Sprint metrics sync",
                    "lag_minutes": 86,
                    "target_lag_minutes": 60,
                    "status": "watch",
                },
                {
                    "artifact": "Daily action logs",
                    "owner": "Daily follow-up log",
                    "lag_minutes": 180,
                    "target_lag_minutes": 240,
                    "status": "healthy",
                },
            ],
        },
        {
            "key": "traceability_coverage",
            "title": "Decision Traceability Coverage",
            "meaning": (
                "Shows whether each high-risk agent workflow was grounded in the required Azure, "
                "tracking, and repository evidence before the answer or proposal was produced."
            ),
            "importance": (
                "Traceability coverage makes audits possible because it ties the agent output "
                "back to the source systems that should have been consulted."
            ),
            "index_column": "workflow",
            "chart_columns": ["coverage_pct"],
            "rows": [
                {
                    "workflow": "Sprint status answer",
                    "required_sources": "Azure daily summary + Task Control snapshot",
                    "coverage_pct": 100,
                    "risk_if_missing": "Story points and blockers may be stale.",
                },
                {
                    "workflow": "Implementation support",
                    "required_sources": "Repo inspection + local validation",
                    "coverage_pct": 92,
                    "risk_if_missing": "Code changes may ignore local repository conventions.",
                },
                {
                    "workflow": "Technical debt preview",
                    "required_sources": "Similarity scan + repo context + child task preview",
                    "coverage_pct": 100,
                    "risk_if_missing": "Duplicate debt or incomplete execution plan.",
                },
                {
                    "workflow": "Tracking sync summary",
                    "required_sources": "AI_Tracking snapshot + metrics log",
                    "coverage_pct": 95,
                    "risk_if_missing": "Daily summary can omit missing files or stale counters.",
                },
            ],
        },
    ]


def build_metric_dictionary() -> list[dict[str, str]]:
    return [
        {
            "group": "Live signal",
            "name": "Usage events",
            "status": "Live",
            "meaning": "How many agent work sessions were recorded in the AI usage log.",
            "importance": "Helps explain operational load and whether audit data is being captured consistently.",
        },
        {
            "group": "Live signal",
            "name": "Logged actions",
            "status": "Live",
            "meaning": "Count of the concrete actions recorded inside those usage events.",
            "importance": "Useful for correlating high activity with PR pressure, blockers, or agent churn.",
        },
        {
            "group": "Live signal",
            "name": "Open PRs",
            "status": "Live",
            "meaning": "Open pull requests listed in the latest current sprint snapshot.",
            "importance": "PR pressure often predicts review bottlenecks and blocked delivery.",
        },
        {
            "group": "Live signal",
            "name": "Remaining story points",
            "status": "Live",
            "meaning": "Outstanding sprint scope from the latest Task Control snapshot.",
            "importance": "Primary burn-down indicator for sprint risk and delivery pace.",
        },
        {
            "group": "Leadership metric",
            "name": "Planned story points",
            "status": "Derived",
            "meaning": "Highest remaining story-point level seen in the sprint snapshot history, used as a practical sprint commitment proxy.",
            "importance": "Gives managers and tech leads a stable baseline for comparing burn, forecast, and scope at risk.",
        },
        {
            "group": "Leadership metric",
            "name": "Actual story points spent",
            "status": "Derived",
            "meaning": "Planned story points minus the latest remaining story points.",
            "importance": "Shows real scope burn instead of only remaining work.",
        },
        {
            "group": "Leadership metric",
            "name": "Expected story points spent",
            "status": "Derived + Mock pacing",
            "meaning": "Expected burn by now using a placeholder sprint elapsed percentage until live sprint calendar fields are exposed.",
            "importance": "Lets leadership compare actual delivery pace against an explicit target instead of intuition.",
        },
        {
            "group": "Leadership metric",
            "name": "Burn variance",
            "status": "Derived + Mock pacing",
            "meaning": "Difference between actual story points spent and expected story points spent.",
            "importance": "A quick negative value shows delivery is trailing plan and needs intervention.",
        },
        {
            "group": "Leadership metric",
            "name": "Forecast delivered story points",
            "status": "Derived + Mock pacing",
            "meaning": "Projected delivered scope at sprint end if the current burn pace continues.",
            "importance": "Gives managers an early outcome estimate before the sprint closes.",
        },
        {
            "group": "Leadership metric",
            "name": "Delivery confidence",
            "status": "Derived + Mock pacing",
            "meaning": "Confidence score penalized by scope at risk, blockers, and overdue PR review age.",
            "importance": "Compresses several execution risks into one management-friendly indicator.",
        },
        {
            "group": "Mock audit signal",
            "name": "MCP Tool Reliability",
            "status": "Mock",
            "meaning": "Success-rate and latency sample for each MCP surface used by the agent.",
            "importance": "Needed to prove whether the agent was operating on healthy infrastructure.",
        },
        {
            "group": "Mock audit signal",
            "name": "Approval Guardrail Coverage",
            "status": "Mock",
            "meaning": "Preview, approval, and blocked-write counters for Azure mutations.",
            "importance": "Confirms that agent writes stay under explicit human approval.",
        },
        {
            "group": "Mock audit signal",
            "name": "Tracking Freshness",
            "status": "Mock",
            "meaning": "Lag between expected and actual updates for the tracked files the observatory reads.",
            "importance": "Prevents a polished dashboard from hiding stale or missing source data.",
        },
        {
            "group": "Mock audit signal",
            "name": "Decision Traceability Coverage",
            "status": "Mock",
            "meaning": "Coverage of required evidence sources for high-risk agent workflows.",
            "importance": "Lets us audit whether the agent followed its operating contract before answering or writing.",
        },
    ]