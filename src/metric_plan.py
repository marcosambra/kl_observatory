from __future__ import annotations

from typing import Any


def build_metric_implementation_plan(tracking_status: dict[str, Any]) -> list[dict[str, str]]:
    availability = _availability_lookup(tracking_status)

    return [
        {
            "audience": "Developer",
            "metric_family": "Current workload",
            "status": "Live",
            "source_files": "AI_Tracking/Task_Control/current-sprint.json",
            "source_available": availability.get("current_sprint", "missing"),
            "contract_basis": "Controle Local Obrigatorio; Inicio de Dia",
            "implementation": "Use user_email, counts.assigned_items, counts.blocked_items, remaining_story_points, remaining_work_hours, and open_prs from the current sprint snapshot.",
        },
        {
            "audience": "Developer",
            "metric_family": "Agent support activity",
            "status": "Live",
            "source_files": "AI_Tracking/Metrics/ai-usage-log.md",
            "source_available": availability.get("usage_log", "missing"),
            "contract_basis": "Controle Local Obrigatorio; metricas operacionais de IA",
            "implementation": "Parse usage sessions, actions executed, and latest sync touchpoint to show how much agent assistance supported the active developer.",
        },
        {
            "audience": "Tech Lead / Manager",
            "metric_family": "Burn and forecast",
            "status": "Live + Derived",
            "source_files": "AI_Tracking/Metrics/sprint-metrics.md; AI_Tracking/Task_Control/current-sprint.json",
            "source_available": _paired_status(availability, "sprint_metrics", "current_sprint"),
            "contract_basis": "Contexto Obrigatorio do Sprint; Controle Local Obrigatorio",
            "implementation": "Combine the sprint burn history with the latest snapshot to compute planned SP proxy, spent SP, expected burn, and sprint-end forecast.",
        },
        {
            "audience": "Audit / Team",
            "metric_family": "Narrative evidence",
            "status": "Live",
            "source_files": "AI_Tracking/Daily_Action_Logs/*.md",
            "source_available": availability.get("daily_logs", "missing"),
            "contract_basis": "Controle Local Obrigatorio; Deteccao de Bloqueios e Retornos",
            "implementation": "Keep daily logs visible so any numeric metric can be traced back to the operational narrative captured by the agent.",
        },
        {
            "audience": "Developer",
            "metric_family": "Returned items and personal churn",
            "status": "Planned",
            "source_files": "AI_Tracking/Task_Control/current-sprint.json + previous snapshots",
            "source_available": availability.get("current_sprint", "missing"),
            "contract_basis": "Deteccao de Bloqueios e Retornos",
            "implementation": "Persist previous current-sprint snapshots and diff assigned items to expose returned work, reassignment churn, and state regressions per developer.",
        },
        {
            "audience": "Developer / Tech Lead",
            "metric_family": "Estimate accuracy",
            "status": "Planned",
            "source_files": "AI_Tracking/Task_Control/current-sprint.json raw_payload",
            "source_available": availability.get("current_sprint", "missing"),
            "contract_basis": "Criacao e Esforco de Work Items",
            "implementation": "Expose original estimate, completed work, remaining work, and story points per item from the saved Azure payload so estimate drift can be measured.",
        },
        {
            "audience": "Manager",
            "metric_family": "Story aging and flow",
            "status": "Planned",
            "source_files": "Azure sprint stories detailed payload cached into AI_Tracking",
            "source_available": "not yet saved",
            "contract_basis": "Contexto Obrigatorio do Sprint",
            "implementation": "Store sprint story state transitions or at least daily snapshots of story metadata so aging, stagnation, and flow efficiency become measurable.",
        },
        {
            "audience": "Tech Lead / Manager",
            "metric_family": "PR turnaround and review depth",
            "status": "Planned",
            "source_files": "current-sprint.json open_prs enriched with review timestamps",
            "source_available": availability.get("current_sprint", "missing"),
            "contract_basis": "Inicio de Dia; progresso do projeto; PRs abertas",
            "implementation": "Persist first-review, approval, and merge timestamps for open PRs so review latency and approval throughput stop relying on age alone.",
        },
    ]


def _availability_lookup(tracking_status: dict[str, Any]) -> dict[str, str]:
    entries = tracking_status.get("entries", []) if isinstance(tracking_status, dict) else []
    return {
        str(entry.get("name", "")): "present" if entry.get("exists") else "missing"
        for entry in entries
    }


def _paired_status(availability: dict[str, str], left_key: str, right_key: str) -> str:
    left = availability.get(left_key, "missing")
    right = availability.get(right_key, "missing")
    return "present" if left == "present" and right == "present" else "partial"