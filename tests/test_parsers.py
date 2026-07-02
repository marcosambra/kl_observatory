from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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


SPRINT_SAMPLE = """# Sprint Metrics Snapshot

| Data | Story Points Restantes | Itens Bloqueados | Resumo |
|---|---:|---:|---|
| 2026-07-01 16:34:20Z | 0 | 0 | Live Azure summary synced into local tracking outputs during validation. |
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
