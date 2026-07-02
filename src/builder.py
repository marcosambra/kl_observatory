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
    project_root = Path(__file__).resolve().parents[1]
    assets_path = project_root / "assets"
    launcher_path = project_root / "src" / "launcher.py"
    streamlit_entry_path = project_root / "dashboard" / "streamlit_app.py"
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
        f"--add-data={_add_data_argument(streamlit_entry_path, 'kl_observatory_resources/dashboard')}",
        f"--add-data={_add_data_argument(streamlit_config_path, '.streamlit')}",
        f"--add-data={_add_data_argument(assets_path, 'kl_observatory_resources/assets')}",
        "--collect-all=streamlit",
        "--collect-all=altair",
        "--collect-all=pyarrow",
        "--collect-submodules=src",
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
