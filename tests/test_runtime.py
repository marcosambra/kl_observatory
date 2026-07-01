from __future__ import annotations

import importlib
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ConfigTests(unittest.TestCase):
    def test_default_database_url_uses_sqlite_file(self) -> None:
        from src import config

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir)
            database_url = config._default_database_url(runtime_root)

            self.assertTrue(database_url.startswith("sqlite:///"))
            self.assertTrue((runtime_root / "var").exists())

    def test_tracking_root_is_discovered_from_parent_chain(self) -> None:
        from src import config

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
    def test_streamlit_wrapper_imports_dashboard_module(self) -> None:
        wrapper_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"

        globals_dict = runpy.run_path(str(wrapper_path))

        self.assertIn("main", globals_dict)


if __name__ == "__main__":
    unittest.main()