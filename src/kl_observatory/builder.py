from __future__ import annotations

import argparse
import platform
from pathlib import Path


def _add_data_argument(source: Path, destination: str) -> str:
    separator = ";" if platform.system() == "Windows" else ":"
    return f"{source}{separator}{destination}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the KL Observatory native executable for the current OS."
    )
    parser.add_argument("--mode", choices=["onefile", "onedir"], default="onefile")
    parser.add_argument("--name", default="kl-observatory")
    return parser.parse_args()


def main() -> None:
    from PyInstaller.__main__ import run as run_pyinstaller

    args = _parse_args()
    project_root = Path(__file__).resolve().parents[2]
    launcher_path = project_root / "src" / "kl_observatory" / "launcher.py"
    dashboard_path = project_root / "src" / "kl_observatory" / "dashboard.py"
    streamlit_config_path = project_root / ".streamlit" / "config.toml"
    build_root = project_root / "build" / "pyinstaller"

    pyinstaller_args = [
        str(launcher_path),
        "--noconfirm",
        "--clean",
        f"--name={args.name}",
        f"--distpath={project_root / 'dist'}",
        f"--workpath={build_root}",
        f"--specpath={build_root}",
        f"--add-data={_add_data_argument(dashboard_path, 'kl_observatory_resources')}",
        f"--add-data={_add_data_argument(streamlit_config_path, '.streamlit')}",
        "--collect-all=streamlit",
        "--collect-all=altair",
        "--collect-all=pyarrow",
        "--collect-submodules=uvicorn",
        "--collect-submodules=sqlalchemy.dialects",
        "--hidden-import=psycopg_binary",
        "--hidden-import=streamlit.web.bootstrap",
    ]

    if args.mode == "onefile":
        pyinstaller_args.append("--onefile")
    else:
        pyinstaller_args.append("--onedir")

    run_pyinstaller(pyinstaller_args)
