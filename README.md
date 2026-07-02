# KL Observatory

Operational observatory for the KwikLedgers agent stack.

This project reads the existing workspace tracking outputs under
`../AI_Tracking`, persists snapshots into Postgres through a small FastAPI
service, and exposes the operational view through Streamlit.

It also ships with a native launcher that starts both FastAPI and Streamlit in
one process tree, plus a Poetry build command that produces the native
executable for the current operating system.

## What It Shows

- agent usage events captured in `AI_Tracking/Metrics/ai-usage-log.md`
- sprint history captured in `AI_Tracking/Metrics/sprint-metrics.md`
- current sprint snapshot from `AI_Tracking/Task_Control/current-sprint.json`
- recent daily action logs from `AI_Tracking/Daily_Action_Logs/`

## Stack

- Streamlit dashboard for the observatory UI
- FastAPI service for sync and overview endpoints
- Postgres for snapshot persistence

## Quick Start

```bash
cp .env.example .env
poetry install
docker compose up --build
```

If `AI_Tracking` lives somewhere else on your machine, point Docker at it with
`TRACKING_SOURCE_DIR`:

```bash
TRACKING_SOURCE_DIR=/absolute/path/to/AI_Tracking docker compose up --build
```

Services:

- Streamlit: `http://localhost:8501`
- FastAPI: `http://localhost:8000`
- Postgres: `localhost:5432`

## Local Python Run

```bash
poetry install
poetry run uvicorn api:app --host 0.0.0.0 --port 8000
poetry run streamlit run dashboard/streamlit_app.py
```

## Unified Launcher

Run both services together from one command:

```bash
poetry run kl-observatory
```

Optional arguments:

```bash
poetry run kl-observatory --host 0.0.0.0 --api-port 8000 --dashboard-port 8501
```

The launcher defaults to a local SQLite database for standalone execution. In
Docker or other managed environments, `DATABASE_URL` can still point to
Postgres.

## Build Native Executable

Build the executable for the current OS:

```bash
poetry install
poetry run build-kl-observatory
```

Output:

- Linux/macOS: `dist/kl-observatory`
- Windows: `dist/kl-observatory.exe`

Notes:

- Native binaries must be built on the target OS. The Linux build produces a
  Linux binary, the Windows build produces a Windows `.exe`, and the macOS
  build produces a macOS binary.
- The build command bundles the Streamlit dashboard entry file and starts both
  FastAPI and Streamlit from the same executable.

## Notes

- The dashboard can fall back to direct file reads if the API is unavailable.
- If the Docker bind source is missing or empty, the API and dashboard now stay
  up and show a tracking warning instead of crashing. Populate
  `TRACKING_SOURCE_DIR` to remove the warning.
- The folder is scaffolded to live as its own repository. Wire it into the
  parent repository as a formal git submodule once the remote repository URL is
  defined.
- The Docker image installs dependencies through Poetry and runs both app
  processes via `poetry run`.
