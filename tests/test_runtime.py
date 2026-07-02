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