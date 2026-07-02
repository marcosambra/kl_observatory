#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def _candidate_workspace_roots() -> list[Path]:
    candidates: list[Path] = []

    for env_name in ("WORKSPACE_ROOT", "KWIKLEDGERS_ROOT_DIR"):
        env_value = os.environ.get(env_name)
        if env_value:
            candidates.append(Path(env_value).expanduser().resolve())

    tracking_root = os.environ.get("TRACKING_ROOT")
    if tracking_root:
        candidates.append(Path(tracking_root).expanduser().resolve().parent)

    candidates.extend(
        [
            PROJECT_ROOT.parent.resolve(),
            Path.cwd().resolve(),
            Path("/workspace").resolve(),
        ]
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def resolve_agent_daily_summary_command() -> tuple[Path, Path, Path]:
    checked_paths: list[str] = []

    for workspace_root in _candidate_workspace_roots():
        runner_path = workspace_root / "agent" / "scripts" / "run_daily_summary.py"
        checked_paths.append(str(runner_path))
        if not runner_path.exists():
            continue

        agent_python = workspace_root / "agent" / "mcp_servers" / ".venv" / "bin" / "python"
        if agent_python.exists():
            return workspace_root, agent_python, runner_path

        return workspace_root, Path(sys.executable), runner_path

    raise FileNotFoundError(
        "Agent daily summary runner not found. Checked: " + ", ".join(checked_paths)
    )


def run_agent_refresh(source: str = "kl-observatory-dashboard", notify: bool = False) -> dict[str, Any]:
    workspace_root, python_path, runner_path = resolve_agent_daily_summary_command()

    command = [str(python_path), str(runner_path), "--source", source]
    if not notify:
        command.append("--skip-notification")

    completed = subprocess.run(
        command,
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        check=False,
    )

    return {
        "source": source,
        "workspace_root": str(workspace_root),
        "runner_path": str(runner_path),
        "python_path": str(python_path),
        "command": command,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dispara o refresh Azure do observatory via runner compartilhado do agente."
    )
    parser.add_argument("--source", default="kl-observatory-dashboard")
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Permite notificacao Windows no runner compartilhado.",
    )
    args = parser.parse_args()

    try:
        result = run_agent_refresh(source=args.source, notify=args.notify)
    except Exception as error:
        print(f"Erro ao executar refresh Azure do observatory: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["returncode"] == 0 else result["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())