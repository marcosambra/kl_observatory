from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Iterator


def _ledger_segments(path: Path) -> list[Path]:
    """Archived ``<stem>.partNNNN<suffix>`` segments in order, then the active file."""
    pattern = re.compile(rf"{re.escape(path.stem)}\.part(\d+)")
    parts = sorted(
        (int(match.group(1)), entry) for entry in (path.parent.iterdir() if path.parent.is_dir() else [])
        if entry.suffix == path.suffix and (match := pattern.fullmatch(entry.stem))
    )
    return [entry for _, entry in parts] + ([path] if path.exists() else [])


def _read_lines(segments: list[Path]) -> Iterator[str]:
    for segment in segments:
        try:
            with segment.open(encoding="utf-8") as stream:
                yield from stream
        except FileNotFoundError:
            continue


def summarize_workflow_events(path: Path) -> dict[str, Any]:
    segments = _ledger_segments(path)
    if not segments:
        return {"source": "unavailable", "observed_runs": None, "outcomes": {},
                "snapshot_confirmed": None, "duplicate_prevented": None,
                "errors": ["request-events.jsonl ausente"]}
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: set[tuple[str, str, str]] = set()
    errors = []
    for number, line in enumerate(_read_lines(segments), 1):
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or event.get("schema_version") != 1:
                raise ValueError("Unsupported request event")
            details = event.get("details", {})
            if not isinstance(details, dict):
                raise ValueError("Unsupported event details")
            node = details.get("node")
            if event.get("kind") != "step" or node not in {"workflow_result", "duplicate_prevented"}:
                continue
            if node == "duplicate_prevented":
                identity = (event.get("request_id"), details.get("run_id"), details.get("observed_at"))
                if any(not isinstance(value, str) or not value.strip() for value in identity):
                    raise ValueError("Duplicate observation identity missing")
                duplicates.add(identity)
                continue
            if any(not isinstance(value, str) or not value.strip() for value in
                   (event.get("request_id"), details.get("run_id"), details.get("outcome"))):
                raise ValueError("Workflow identity missing")
            latest[(event["request_id"], details["run_id"])] = details
        except (ValueError, TypeError):
            errors.append(f"Evento inválido na linha {number}")
    outcomes: dict[str, int] = {}
    for details in latest.values():
        outcome = details["outcome"]
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {"source": "partial" if errors else "real", "observed_runs": len(latest),
            "outcomes": outcomes,
            "snapshot_confirmed": sum(item.get("reason") == "snapshot_confirmed" for item in latest.values()),
            "duplicate_prevented": len(duplicates),
            "errors": errors}


def build_tracking_insights(tracking_payload: dict[str, Any]) -> dict[str, Any]:
    optimization = tracking_payload.get("optimization_report", {})
    storypoints = tracking_payload.get("storypoints_report", {})
    repo_context = tracking_payload.get("repo_work_item_context", {})
    audit = tracking_payload.get("audit_log", {})

    optimization_metrics = optimization.get("metrics", {})
    storypoint_metrics = storypoints.get("metrics", {})
    debt_summary = repo_context.get("technical_debt_summary", {})
    preview_summary = repo_context.get("preview_summary", {})
    audit_summary = audit.get("summary", {})
    usage_events = tracking_payload.get("usage_events", [])
    runtime_usage_events = [
        event for event in usage_events
        if str(event.get("runtime_flow_name") or "").strip()
    ]
    runtime_flow_counts: dict[str, int] = {}
    runtime_status_counts: dict[str, int] = {}
    for event in runtime_usage_events:
        flow_name = str(event.get("runtime_flow_name") or "unknown")
        final_status = str(event.get("runtime_final_status") or "unknown")
        runtime_flow_counts[flow_name] = runtime_flow_counts.get(flow_name, 0) + 1
        runtime_status_counts[final_status] = runtime_status_counts.get(final_status, 0) + 1

    return {
        "headline": {
            "hours_saved_per_month": optimization_metrics.get("hours_saved_per_month", 0),
            "impact_index_pct": storypoint_metrics.get("impact_index_pct", 0.0),
            "cycle_time_reduction_pct": storypoint_metrics.get("cycle_time_reduction_pct", 0.0),
            "repo_count": optimization_metrics.get("top_level_systems", 0),
            "technical_debt_items": debt_summary.get("total_items", 0),
            "preview_entries": preview_summary.get("total_preview_entries", 0),
            "audit_errors": audit_summary.get("error_entries", 0),
            "runtime_usage_events": len(runtime_usage_events),
        },
        "optimization": optimization_metrics,
        "storypoints": storypoint_metrics,
        "repo_context": {
            "technical_debt_summary": debt_summary,
            "preview_summary": preview_summary,
        },
        "audit": audit_summary,
        "runtime_usage": {
            "events": runtime_usage_events,
            "flow_counts": runtime_flow_counts,
            "status_counts": runtime_status_counts,
        },
        "workflow_results": tracking_payload.get("workflow_results", {"source": "unavailable"}),
    }


def build_metric_dictionary_entries() -> list[dict[str, str]]:
    return [
        {
            "group": "AI_Tracking report metric",
            "name": "Hours saved per month",
            "status": "Live from report",
            "meaning": "Projected engineering hours saved per month from the optimization report's quantified AI impact model.",
            "importance": "Gives leadership a direct operational value estimate from the tracked optimization report.",
        },
        {
            "group": "AI_Tracking report metric",
            "name": "AI impact index",
            "status": "Live from report",
            "meaning": "Composite impact score from cycle time, rework, and defect reductions recorded in the story-point objective report.",
            "importance": "Summarizes whether AI usage improved delivery across time and quality, not just estimate points.",
        },
        {
            "group": "AI_Tracking report metric",
            "name": "Technical debt coverage",
            "status": "Live from repo context",
            "meaning": "Count and state spread of technical debt items cached under Repo_Work_Item_Context.",
            "importance": "Shows whether repository-level debt visibility is broad enough to support planning and duplicate detection.",
        },
        {
            "group": "AI_Tracking report metric",
            "name": "Preview cache volume",
            "status": "Live from repo context",
            "meaning": "Number of technical debt preview entries currently saved in the preview cache files.",
            "importance": "Confirms that pre-write technical debt evidence is actually being retained for auditability.",
        },
        {
            "group": "AI_Tracking report metric",
            "name": "MCP audit error count",
            "status": "Live from audit log",
            "meaning": "Number of ERROR lines found in the MCP audit log snapshot the observatory can read.",
            "importance": "Provides a direct signal for integration failures across the agent and MCP surfaces.",
        },
        {
            "group": "LangGraph runtime metric",
            "name": "Runtime usage events",
            "status": "Live from AI usage log",
            "meaning": "Count of usage-log entries emitted directly by the LangGraph runtime CLIs using the runtime:* title pattern.",
            "importance": "Shows whether the new runtime is already producing observable execution traces consumable by the observatory stack.",
        },
        {
            "group": "LangGraph runtime metric",
            "name": "Runtime flow distribution",
            "status": "Live from AI usage log",
            "meaning": "Breakdown of runtime events by flow name, such as daily summary, story PR, branch association, and story status transition.",
            "importance": "Helps identify which LangGraph surfaces are actually being exercised in practice and where failures concentrate.",
        },
    ]


def parse_optimization_report(markdown: str) -> dict[str, Any]:
    metrics = {
        "top_level_systems": _extract_int(markdown, r"Sistemas/diretorios de primeiro nivel: \*\*(?P<value>[\d.]+)\*\*"),
        "active_systems": _extract_int(markdown, r"Sistemas de software ativos .*: \*\*(?P<value>[\d.]+)\*\*"),
        "docker_compose_files": _extract_int(markdown, r"Total de arquivos docker-compose .*: \*\*(?P<value>[\d.]+)\*\*"),
        "primary_loc": _extract_int(markdown, r"\*\*(?P<value>[\d.]+) LOC\*\*"),
        "hours_saved_per_month": _extract_int(markdown, r"\*\*(?P<value>[\d.]+)h/mes\*\*"),
        "onboarding_savings_min_hours": _extract_float(markdown, r"Economia esperada de onboarding: \*\*(?P<value>[\d.,]+)h"),
        "implementation_speed_min_pct": _extract_float(markdown, r"Reducao de tempo de implementacao: \*\*(?P<value>[\d.,]+)%"),
        "implementation_speed_max_pct": _extract_float(markdown, r"Reducao de tempo de implementacao: \*\*[\d.,]+% a (?P<value>[\d.,]+)%\*\*"),
        "test_speed_min_pct": _extract_float(markdown, r"Reducao de tempo de escrita de testes: \*\*(?P<value>[\d.,]+)%"),
        "test_speed_max_pct": _extract_float(markdown, r"Reducao de tempo de escrita de testes: \*\*[\d.,]+% a (?P<value>[\d.,]+)%\*\*"),
        "review_speed_min_pct": _extract_float(markdown, r"Reducao de tempo de preparacao para revisao: \*\*(?P<value>[\d.,]+)%"),
        "review_speed_max_pct": _extract_float(markdown, r"Reducao de tempo de preparacao para revisao: \*\*[\d.,]+% a (?P<value>[\d.,]+)%\*\*"),
    }
    return {"content": markdown, "metrics": metrics}


def parse_storypoints_report(markdown: str) -> dict[str, Any]:
    metrics = {
        "impact_index_pct": _extract_float(markdown, r"\*\*IndiceImpactoIA\*\* \| .+ \| \*\*(?P<value>[\d.,]+)%\*\*"),
        "cycle_time_baseline_hours": _extract_float(markdown, r"Cycle time mediano por item \| (?P<value>[\d.,]+)h \|"),
        "cycle_time_with_ai_hours": _extract_float(markdown, r"Cycle time mediano por item \| [\d.,]+h \| (?P<value>[\d.,]+)h \|"),
        "cycle_time_reduction_pct": _extract_float(markdown, r"Cycle time mediano por item \| [^|]+\| [^|]+\| (?P<value>-?[\d.,]+)% \|"),
        "rework_reduction_pct": _extract_float(markdown, r"Retrabalho por item \| [^|]+\| [^|]+\| (?P<value>-?[\d.,]+)% \|"),
        "defect_reduction_pct": _extract_float(markdown, r"Defeitos pos-release por 10 itens \| [^|]+\| [^|]+\| (?P<value>-?[\d.,]+)% \|"),
        "simplified_sp_delta_pct": _extract_float(markdown, r"Tarefa simplificada com IA \| 3 SP \| 2 SP \| (?P<value>-?[\d.,]+)%"),
        "expanded_sp_delta_pct": _extract_float(markdown, r"Tarefa com escopo ampliado ou reestimada \| 3 SP \| 4 SP \| (?P<value>[\d.,]+)%"),
    }
    return {"content": markdown, "metrics": metrics}


def summarize_repo_work_item_context(repo_context_root: Path) -> dict[str, Any]:
    previews_root = repo_context_root / "technical_debt_previews"
    debts_root = repo_context_root / "technical_debts"

    preview_files = sorted(previews_root.glob("*.json")) if previews_root.exists() else []
    debt_files = sorted(debts_root.glob("*.json")) if debts_root.exists() else []

    preview_entries: list[dict[str, Any]] = []
    preview_total = 0
    for path in preview_files:
        payload = _read_json_file(path)
        entries = payload.get("preview_entries", []) if isinstance(payload, dict) else []
        preview_total += len(entries)
        preview_entries.append(
            {
                "repository_name": payload.get("repository_name", path.stem) if isinstance(payload, dict) else path.stem,
                "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
                "preview_entries": len(entries),
            }
        )

    debt_rows: list[dict[str, Any]] = []
    debt_state_counts: dict[str, int] = {}
    total_debts = 0
    for path in debt_files:
        payload = _read_json_file(path)
        debts = payload.get("technical_debts", []) if isinstance(payload, dict) else []
        total_debts += len(debts)
        for debt in debts:
            state = str(debt.get("state", "unknown"))
            debt_state_counts[state] = debt_state_counts.get(state, 0) + 1
        debt_rows.append(
            {
                "repository_name": payload.get("repository_name", path.stem) if isinstance(payload, dict) else path.stem,
                "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
                "technical_debts": len(debts),
            }
        )

    return {
        "preview_summary": {
            "files": preview_entries,
            "total_preview_files": len(preview_files),
            "total_preview_entries": preview_total,
        },
        "technical_debt_summary": {
            "files": debt_rows,
            "total_debt_files": len(debt_files),
            "total_items": total_debts,
            "state_counts": debt_state_counts,
        },
    }


def summarize_audit_log(content: str, line_limit: int = 80) -> dict[str, Any]:
    lines = [line for line in content.splitlines() if line.strip()]
    last_lines = lines[-line_limit:]
    summary = {
        "total_entries": len(lines),
        "error_entries": sum(" ERROR " in line for line in lines),
        "warning_entries": sum(" WARNING " in line for line in lines),
        "azure_events": sum("kwikledgers.azure_devops" in line for line in lines),
        "local_tracking_events": sum("kwikledgers.local_tracking" in line for line in lines),
        "windows_events": sum("kwikledgers.windows" in line for line in lines),
    }
    return {"summary": summary, "tail": last_lines}


def _read_json_file(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _extract_int(markdown: str, pattern: str) -> int:
    value = _extract_float(markdown, pattern)
    return int(value)


def _extract_float(markdown: str, pattern: str) -> float:
    match = re.search(pattern, markdown)
    if not match:
        return 0.0
    return float(match.group("value").replace(".", "").replace(",", "."))