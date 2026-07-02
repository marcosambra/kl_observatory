from __future__ import annotations

import importlib
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ConfigTests(unittest.TestCase):
    def test_default_database_url_uses_sqlite_file(self) -> None:
        from api import config

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            database_url = config._default_database_url(runtime_root)

            self.assertTrue(database_url.startswith("sqlite:///"))
            self.assertTrue((runtime_root / "var").exists())

    def test_tracking_root_is_discovered_from_parent_chain(self) -> None:
        from api import config

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            tracking_root = workspace_root / "AI_Tracking"
            nested_root = workspace_root / "kl_observatory" / "dist"
            tracking_root.mkdir(parents=True)
            nested_root.mkdir(parents=True)

            discovered = config._discover_tracking_root(nested_root)

            self.assertEqual(discovered, tracking_root)


class BuilderTests(unittest.TestCase):
    def test_add_data_argument_uses_platform_separator(self) -> None:
        from src.builder import _add_data_argument

        source = Path("/tmp/dashboard.py")

        with patch("platform.system", return_value="Linux"):
            self.assertEqual(
                _add_data_argument(source, "bundle"),
                "/tmp/dashboard.py:bundle",
            )

        with patch("platform.system", return_value="Windows"):
            self.assertEqual(
                _add_data_argument(source, "bundle"),
                "/tmp/dashboard.py;bundle",
            )


class DashboardRuntimeTests(unittest.TestCase):
    def test_top_level_api_package_exports_fastapi_app(self) -> None:
        module = importlib.import_module("api")

        self.assertTrue(hasattr(module, "app"))

    def test_streamlit_wrapper_imports_dashboard_module(self) -> None:
        wrapper_path = Path(__file__).resolve().parents[1] / "dashboard" / "streamlit_app.py"

        globals_dict = runpy.run_path(str(wrapper_path))

        self.assertIn("main", globals_dict)

    def test_dashboard_logo_path_points_to_existing_asset(self) -> None:
        from src.dashboard import _logo_path

        self.assertTrue(_logo_path().exists())
        self.assertEqual(_logo_path().name, "ambra.png")

    def test_mock_audit_signals_include_descriptions_and_rows(self) -> None:
        from src.mock_data import (
            build_metric_dictionary,
            build_mock_audit_signals,
            build_mock_leadership_assumptions,
        )

        signals = build_mock_audit_signals()
        dictionary = build_metric_dictionary()
        assumptions = build_mock_leadership_assumptions()

        self.assertGreaterEqual(len(signals), 4)
        self.assertGreaterEqual(len(dictionary), 17)
        self.assertIn("sprint_elapsed_pct", assumptions)

        for signal in signals:
            self.assertTrue(signal["title"])
            self.assertTrue(signal["meaning"])
            self.assertTrue(signal["importance"])
            self.assertTrue(signal["rows"])

    def test_leadership_metrics_calculate_expected_and_forecast_values(self) -> None:
        from src.leadership_metrics import build_leadership_metrics
        from src.mock_data import build_mock_leadership_assumptions

        overview = {
            "current_snapshot": {
                "counts": {
                    "assigned_items": 5,
                    "blocked_items": 1,
                    "open_prs": 3,
                    "user_stories": 4,
                },
                "remaining_story_points": 3,
                "open_prs": [
                    {"repository": "portal_backend", "age_days": 3},
                    {"repository": "portal_frontend", "age_days": 1},
                    {"repository": "accounting", "age_days": 4},
                ],
            },
            "sprint_metrics": [
                {"timestamp": "2026-07-01T10:00:00+00:00", "remaining_story_points": 13, "blocked_items": 1},
                {"timestamp": "2026-07-02T10:00:00+00:00", "remaining_story_points": 3, "blocked_items": 1},
            ],
            "usage_events": [
                {"actions": ["sync", "summarize"]},
                {"actions": ["validate"]},
            ],
        }

        metrics = build_leadership_metrics(
            overview,
            build_mock_leadership_assumptions(),
        )

        self.assertEqual(metrics["tech_lead"]["planned_story_points"], 13.0)
        self.assertEqual(metrics["tech_lead"]["actual_spent_story_points"], 10.0)
        self.assertGreater(metrics["tech_lead"]["expected_spent_story_points"], 8.0)
        self.assertGreater(metrics["manager"]["forecast_delivered_story_points"], 12.0)
        self.assertGreater(metrics["manager"]["delivery_confidence_pct"], 0.0)

    def test_individual_metrics_calculate_personal_workload_and_support(self) -> None:
        from src.individual_metrics import build_individual_metrics

        overview = {
            "current_snapshot": {
                "user_email": "dev@kwikledgers.com",
                "counts": {
                    "assigned_items": 4,
                    "blocked_items": 1,
                    "open_prs": 2,
                    "user_stories": 3,
                },
                "remaining_story_points": 6,
                "remaining_work_hours": 18,
                "open_prs": [
                    {"repository": "portal_backend", "age_days": 3},
                    {"repository": "portal_frontend", "age_days": 1},
                ],
            },
            "sprint_metrics": [
                {"timestamp": "2026-07-01T10:00:00+00:00", "remaining_story_points": 9, "blocked_items": 0},
                {"timestamp": "2026-07-02T10:00:00+00:00", "remaining_story_points": 6, "blocked_items": 1},
            ],
            "usage_events": [
                {"timestamp": "2026-07-02T11:00:00+00:00", "title": "Daily sync via agent", "actions": ["sync", "summarize"]},
                {"timestamp": "2026-07-02T12:00:00+00:00", "title": "Validation pass", "actions": ["validate"]},
            ],
        }

        metrics = build_individual_metrics(overview)

        self.assertEqual(metrics["user_email"], "dev@kwikledgers.com")
        self.assertEqual(metrics["current"]["assigned_items"], 4)
        self.assertEqual(metrics["derived"]["recent_story_points_burn"], 3.0)
        self.assertEqual(metrics["derived"]["remaining_hours_per_item"], 4.5)
        self.assertEqual(metrics["derived"]["actions_per_session"], 1.5)

    def test_metric_plan_maps_contract_to_saved_sources(self) -> None:
        from src.metric_plan import build_metric_implementation_plan

        plan = build_metric_implementation_plan(
            {
                "entries": [
                    {"name": "usage_log", "exists": True},
                    {"name": "sprint_metrics", "exists": True},
                    {"name": "current_sprint", "exists": True},
                    {"name": "daily_logs", "exists": False},
                ]
            }
        )

        self.assertGreaterEqual(len(plan), 8)
        self.assertTrue(any(row["audience"] == "Developer" for row in plan))
        self.assertTrue(any("Controle Local Obrigatorio" in row["contract_basis"] for row in plan))
        self.assertTrue(any("AI_Tracking/Task_Control/current-sprint.json" in row["source_files"] for row in plan))

    def test_tracking_insights_use_full_ai_tracking_payload(self) -> None:
        from src.tracking_insights import build_tracking_insights

        insights = build_tracking_insights(
            {
                "optimization_report": {"metrics": {"hours_saved_per_month": 262, "top_level_systems": 26}},
                "storypoints_report": {"metrics": {"impact_index_pct": 41.67, "cycle_time_reduction_pct": -33.33}},
                "repo_work_item_context": {
                    "technical_debt_summary": {"total_items": 12},
                    "preview_summary": {"total_preview_entries": 4},
                },
                "audit_log": {"summary": {"error_entries": 3}},
            }
        )

        self.assertEqual(insights["headline"]["hours_saved_per_month"], 262)
        self.assertEqual(insights["headline"]["technical_debt_items"], 12)
        self.assertEqual(insights["headline"]["preview_entries"], 4)
        self.assertEqual(insights["headline"]["audit_errors"], 3)

    def test_tracking_overview_includes_extended_ai_tracking_surfaces(self) -> None:
        from api.services import build_tracking_overview

        with tempfile.TemporaryDirectory() as temp_dir:
            tracking_root = Path(temp_dir) / "AI_Tracking"
            metrics_root = tracking_root / "Metrics"
            repo_context_root = tracking_root / "Repo_Work_Item_Context"
            previews_root = repo_context_root / "technical_debt_previews"
            debts_root = repo_context_root / "technical_debts"
            audit_root = tracking_root / "Audit"
            daily_logs_root = tracking_root / "Daily_Action_Logs"
            task_control_root = tracking_root / "Task_Control"

            metrics_root.mkdir(parents=True)
            previews_root.mkdir(parents=True)
            debts_root.mkdir(parents=True)
            audit_root.mkdir(parents=True)
            daily_logs_root.mkdir(parents=True)
            task_control_root.mkdir(parents=True)

            (metrics_root / "ai-usage-log.md").write_text(
                """# AI Usage Metrics Log\n\n## 2026-07-02 11:00:00Z - Daily sync via agent\n\nResumo: Daily sync completed with 0 assigned items, 0 blocked items, and 10 open PRs.\nStory points restantes: 0\nItens bloqueados: 0\nAcoes executadas:\n- Generated live Azure daily summary\n""",
                encoding="utf-8",
            )
            (metrics_root / "sprint-metrics.md").write_text(
                """# Sprint Metrics Snapshot\n\n| Data | Story Points Restantes | Itens Bloqueados | Resumo |\n|---|---:|---:|---|\n| 2026-07-02 11:00:00Z | 0 | 0 | Daily sync completed with 0 assigned items, 0 blocked items, and 10 open PRs. |\n""",
                encoding="utf-8",
            )
            (metrics_root / "AI_Optimization_Metrics_Report.md").write_text(
                "Sistemas/diretorios de primeiro nivel: **26**\nResultado: **262h/mes**\nReducao de tempo de implementacao: **18% a 32%**\nReducao de tempo de escrita de testes: **25% a 45%**\nReducao de tempo de preparacao para revisao: **20% a 35%**\nVolume de linhas nas linguagens principais (`.php`, `.ts`, `.js`, `.py`, excluindo pastas de dependencia/build): **82.962 LOC**\nEconomia esperada de onboarding: **6,3h a 9,45h por novo desenvolvedor**\n",
                encoding="utf-8",
            )
            (metrics_root / "AI_StoryPoints_Objective_Report.md").write_text(
                "| Metrica | Sem IA (baseline) | Com IA | Variacao |\n|---------|------------------|--------|----------|\n| Cycle time mediano por item | 24h | 16h | -33,33% |\n| Retrabalho por item | 6h | 3h | -50,00% |\n| Defeitos pos-release por 10 itens | 2 | 1 | -50,00% |\n| **IndiceImpactoIA** | — | — | **41,67%** |\n| Tarefa simplificada com IA | 3 SP | 2 SP | -33,33% |\n| Tarefa com escopo ampliado ou reestimada | 3 SP | 4 SP | +33,33% |\n",
                encoding="utf-8",
            )
            (previews_root / "repo.json").write_text(
                '{"repository_name":"repo","updated_at":"2026-07-02T00:00:00Z","preview_entries":[{"title":"preview"}]}',
                encoding="utf-8",
            )
            (debts_root / "repo.json").write_text(
                '{"repository_name":"repo","updated_at":"2026-07-02T00:00:00Z","technical_debts":[{"state":"New"},{"state":"Closed"}]}',
                encoding="utf-8",
            )
            (audit_root / "mcp-audit.log").write_text(
                "2026-07-02 10:00:00,000 - kwikledgers.azure_devops - INFO - ok\n2026-07-02 10:01:00,000 - kwikledgers.local_tracking - ERROR - boom\n",
                encoding="utf-8",
            )
            (task_control_root / "current-sprint.md").write_text(
                "# Sprint Control Snapshot\n",
                encoding="utf-8",
            )

            overview = build_tracking_overview(tracking_root=tracking_root)

        self.assertIn("optimization_report", overview)
        self.assertIn("storypoints_report", overview)
        self.assertIn("repo_work_item_context", overview)
        self.assertIn("audit_log", overview)
        self.assertIn("current_sprint_markdown", overview)
        self.assertEqual(overview["optimization_report"]["metrics"]["hours_saved_per_month"], 262)
        self.assertEqual(overview["repo_work_item_context"]["technical_debt_summary"]["total_items"], 2)
        self.assertEqual(overview["audit_log"]["summary"]["error_entries"], 1)


class TrackingOverviewTests(unittest.TestCase):
    def test_generated_at_normalization_parses_iso_strings(self) -> None:
        from api.services import _normalize_generated_at

        normalized = _normalize_generated_at("2026-07-01T16:54:54+00:00")

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.isoformat(), "2026-07-01T16:54:54+00:00")

    def test_build_tracking_overview_handles_missing_tracking_root(self) -> None:
        from api.services import build_tracking_overview

        with tempfile.TemporaryDirectory() as temp_dir:
            missing_root = Path(temp_dir) / "AI_Tracking"

            overview = build_tracking_overview(tracking_root=missing_root)

        self.assertEqual(overview["usage_events"], [])
        self.assertEqual(overview["sprint_metrics"], [])
        self.assertEqual(overview["current_snapshot"], {})
        self.assertFalse(overview["tracking_status"]["available"])
        self.assertGreaterEqual(len(overview["tracking_status"]["missing_paths"]), 4)
        self.assertGreaterEqual(len(overview["tracking_status"]["entries"]), 9)

    def test_build_tracking_overview_derives_current_snapshot_from_metrics(self) -> None:
        from api.services import build_tracking_overview

        with tempfile.TemporaryDirectory() as temp_dir:
            tracking_root = Path(temp_dir) / "AI_Tracking"
            metrics_root = tracking_root / "Metrics"
            daily_logs_root = tracking_root / "Daily_Action_Logs"
            task_control_root = tracking_root / "Task_Control"

            metrics_root.mkdir(parents=True)
            daily_logs_root.mkdir(parents=True)
            task_control_root.mkdir(parents=True)

            (metrics_root / "ai-usage-log.md").write_text(
                """# AI Usage Metrics Log\n\n## 2026-07-02 11:00:00Z - Daily sync via agent\n\nResumo: Daily sync completed with 0 assigned items, 0 blocked items, and 10 open PRs.\nStory points restantes: 0\nItens bloqueados: 0\nAcoes executadas:\n- Generated live Azure daily summary\n""",
                encoding="utf-8",
            )
            (metrics_root / "sprint-metrics.md").write_text(
                """# Sprint Metrics Snapshot\n\n| Data | Story Points Restantes | Itens Bloqueados | Resumo |\n|---|---:|---:|---|\n| 2026-07-02 11:00:00Z | 0 | 0 | Daily sync completed with 0 assigned items, 0 blocked items, and 10 open PRs. |\n""",
                encoding="utf-8",
            )

            overview = build_tracking_overview(tracking_root=tracking_root)

        self.assertEqual(overview["current_snapshot"]["snapshot_source"], "derived_from_metrics")
        self.assertEqual(overview["current_snapshot"]["counts"]["open_prs"], 10)
        self.assertEqual(overview["current_snapshot"]["remaining_story_points"], 0)
        self.assertTrue(overview["tracking_status"]["available"])
        current_sprint_entry = next(
            entry for entry in overview["tracking_status"]["entries"] if entry["name"] == "current_sprint"
        )
        self.assertEqual(current_sprint_entry["state"], "derived")


class ApiStatusTests(unittest.TestCase):
    def test_status_route_returns_tracking_status(self) -> None:
        from api.app import status

        payload = status()

        self.assertIn("root", payload)
        self.assertIn("available", payload)
        self.assertIn("entries", payload)


if __name__ == "__main__":
    unittest.main()