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
        self.assertGreaterEqual(len(dictionary), 12)
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


class TrackingOverviewTests(unittest.TestCase):
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
        self.assertEqual(len(overview["tracking_status"]["entries"]), 4)


class ApiStatusTests(unittest.TestCase):
    def test_status_route_returns_tracking_status(self) -> None:
        from api.app import status

        payload = status()

        self.assertIn("root", payload)
        self.assertIn("available", payload)
        self.assertIn("entries", payload)


if __name__ == "__main__":
    unittest.main()