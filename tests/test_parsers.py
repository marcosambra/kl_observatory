from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from src.tracking_insights import summarize_workflow_events

from src.parsers import (
    load_current_sprint,
    parse_ai_usage_log,
    parse_sprint_metrics,
)


USAGE_SAMPLE = """# AI Usage Metrics Log

## 2026-07-01 16:34:20Z - Azure MCP live validation

Resumo: Live Azure summary synced into local tracking outputs during validation.
Story points restantes: 0
Itens bloqueados: 0
Acoes executadas:
- Validated Azure MCP daily summary against live environment
- Synchronized local tracking outputs from live Azure summary
"""


USAGE_SAMPLE_WITH_DECIMAL_STORY_POINTS = """# AI Usage Metrics Log

## 2026-07-02 12:00:12Z - Resumo diario agendado

Resumo: Resumo do sprint com story points formatados como decimal.
Story points restantes: 34.0
Itens bloqueados: 0
Acoes executadas:
- scheduled_daily_summary
"""


RUNTIME_USAGE_SAMPLE = """# AI Usage Metrics Log

## 2026-07-28 01:22:00Z - runtime:story_status_transition:completed

Resumo: Transicao concluida.
Story points restantes: 0
Itens bloqueados: 0
Acoes executadas:
- source=story-status-cli
- run_id=run-123
- correlation_id=corr-123
- node=execute_status_transition status=completed
"""


SPRINT_SAMPLE = """# Sprint Metrics Snapshot

| Data | Story Points Restantes | Itens Bloqueados | Resumo |
|---|---:|---:|---|
| 2026-07-01 16:34:20Z | 0 | 0 | Live Azure summary synced into local tracking outputs during validation. |
"""


SPRINT_SAMPLE_WITH_PLACEHOLDERS = """# Sprint Metrics Snapshot

| Data | Story Points Restantes | Itens Bloqueados | Resumo |
|---|---:|---:|---|
| 2026-07-02 12:00:12Z | - | 0 | Metrics snapshot still pending story point sync. |
"""


CURRENT_SPRINT_SAMPLE = {
    "generated_at": "2026-07-01T16:54:54.269432Z",
    "project": "Kwik Ledgers",
    "user_email": "marcos.pereira@ambrait.com",
    "counts": {
        "assigned_items": 0,
        "blocked_items": 0,
        "open_prs": 10,
        "user_stories": 0,
    },
    "remaining_story_points": 0,
    "remaining_work_hours": 0,
    "open_prs": [],
    "items": [],
    "blocked_items": [],
    "returned_items": [],
}


class ParserTests(unittest.TestCase):
    def test_workflow_ledger_counts_latest_observed_run_without_summing_spans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request-events.jsonl"
            self.assertEqual(summarize_workflow_events(path)["source"], "unavailable")
            def event(outcome, reason):
                return {"schema_version": 1, "kind": "step", "request_id": "request",
                        "duration_ms": 1000, "details": {"node": "workflow_result",
                        "run_id": "run", "outcome": outcome, "reason": reason}}
            path.write_text("\n".join(json.dumps(value) for value in (
                event("waiting", "snapshot_not_checked"), event("completed", "snapshot_confirmed"))),
                encoding="utf-8")
            result = summarize_workflow_events(path)
            self.assertEqual(result["source"], "real")
            self.assertEqual(result["observed_runs"], 1)
            self.assertEqual(result["outcomes"], {"completed": 1})
            self.assertEqual(result["snapshot_confirmed"], 1)
            self.assertNotIn("duration_ms", result)
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n{broken")
            result = summarize_workflow_events(path)
            self.assertEqual(result["source"], "partial")
            self.assertEqual(len(result["errors"]), 1)

    def test_parse_ai_usage_log_extracts_actions(self) -> None:
        records = parse_ai_usage_log(USAGE_SAMPLE)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Azure MCP live validation")
        self.assertEqual(records[0].remaining_story_points, 0)
        self.assertEqual(len(records[0].actions), 2)

    def test_parse_sprint_metrics_extracts_rows(self) -> None:
        records = parse_sprint_metrics(SPRINT_SAMPLE)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].blocked_items, 0)
        self.assertEqual(records[0].summary, "Live Azure summary synced into local tracking outputs during validation.")

    def test_parse_sprint_metrics_accepts_placeholder_story_points(self) -> None:
        records = parse_sprint_metrics(SPRINT_SAMPLE_WITH_PLACEHOLDERS)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].remaining_story_points, 0)
        self.assertEqual(records[0].blocked_items, 0)

    def test_parse_ai_usage_log_accepts_decimal_story_points(self) -> None:
        records = parse_ai_usage_log(USAGE_SAMPLE_WITH_DECIMAL_STORY_POINTS)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].remaining_story_points, 34)
        self.assertEqual(records[0].blocked_items, 0)

    def test_parse_ai_usage_log_extracts_langgraph_runtime_metadata(self) -> None:
        records = parse_ai_usage_log(RUNTIME_USAGE_SAMPLE)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].runtime_flow_name, "story_status_transition")
        self.assertEqual(records[0].runtime_final_status, "completed")
        self.assertEqual(records[0].runtime_source, "story-status-cli")
        self.assertEqual(records[0].runtime_run_id, "run-123")
        self.assertEqual(records[0].runtime_correlation_id, "corr-123")

    def test_load_current_sprint_reads_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "current-sprint.json"
            temp_path.write_text(json.dumps(CURRENT_SPRINT_SAMPLE), encoding="utf-8")

            record = load_current_sprint(temp_path)

        self.assertEqual(record.project, "Kwik Ledgers")
        self.assertEqual(record.counts["open_prs"], 10)
        self.assertEqual(record.remaining_work_hours, 0)


if __name__ == "__main__":
    unittest.main()
