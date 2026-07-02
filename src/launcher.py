from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path

import requests
import uvicorn
from streamlit.web.bootstrap import load_config_options
from streamlit.web.bootstrap import run as run_streamlit
from api.app import app



def _resource_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))

    return Path(__file__).resolve().parent


def _dashboard_script_path() -> Path:
    if getattr(sys, "frozen", False):
        return _resource_base() / "kl_observatory_resources" / "dashboard" / "streamlit_app.py"

    return Path(__file__).resolve().parents[1] / "dashboard" / "streamlit_app.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the KL Observatory API and Streamlit dashboard together."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--dashboard-port", type=int, default=8501)
    parser.add_argument("--tracking-root")
    parser.add_argument("--database-url")
    parser.add_argument("--log-level", default="info")
    return parser.parse_args()


def _wait_for_api(api_base_url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            response = requests.get(f"{api_base_url}/health", timeout=1)
            response.raise_for_status()
            return
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(0.25)

    raise RuntimeError(f"API failed to start at {api_base_url}") from last_error


def _start_api_server(host: str, api_port: int, log_level: str) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(
        app,
        host=host,
        port=api_port,
        log_level=log_level,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="kl-observatory-api", daemon=True)
    thread.start()
    return server, thread


def main() -> None:
    args = _parse_args()

    if args.tracking_root:
        os.environ["TRACKING_ROOT"] = args.tracking_root
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    api_base_url = f"http://127.0.0.1:{args.api_port}"
    os.environ["API_BASE_URL"] = api_base_url
    streamlit_flags = {
        "global_developmentMode": False,
        "server_headless": True,
        "server_address": args.host,
        "server_port": args.dashboard_port,
        "browser_serverAddress": "127.0.0.1",
        "browser_serverPort": args.dashboard_port,
        "browser_gatherUsageStats": False,
    }

    server, thread = _start_api_server(args.host, args.api_port, args.log_level)

    def shutdown(*_: object) -> None:
        server.should_exit = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        _wait_for_api(api_base_url)
        print(f"KL Observatory API: {api_base_url}")
        print(f"KL Observatory Dashboard: http://127.0.0.1:{args.dashboard_port}")
        load_config_options(streamlit_flags)
        run_streamlit(
            str(_dashboard_script_path()),
            False,
            [],
            streamlit_flags,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()