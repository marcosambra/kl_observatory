# KL Observatory

Operational observatory for the KwikLedgers agent stack.

This project reads the existing workspace tracking outputs under
`../AI_Tracking`, persists snapshots into Postgres through a small FastAPI
service, and exposes the operational view through Streamlit.

It also ships with a native launcher that starts both FastAPI and Streamlit in
one process tree, plus a Poetry build command that produces the native
executable for the current operating system.

The dashboard now uses native Streamlit layout primitives and built-in page
navigation rather than injected HTML. The visual theme lives in
`.streamlit/config.toml`.

## What It Shows

- agent usage events captured in `AI_Tracking/Metrics/ai-usage-log.md`
- sprint history captured in `AI_Tracking/Metrics/sprint-metrics.md`
- current sprint snapshot from `AI_Tracking/Task_Control/current-sprint.json`
- recent daily action logs from `AI_Tracking/Daily_Action_Logs/`
- structured LangGraph runtime usage signals derived from `runtime:*` events emitted into `AI_Tracking/Metrics/ai-usage-log.md`
- mocked audit telemetry for MCP tool reliability, approval guardrails,
  tracking freshness, and decision traceability coverage

## Dashboard Pages

- `Operations Overview`: live AI_Tracking metrics for sprint movement, usage,
  PR pressure, LangGraph runtime usage, and daily logs
- `Audit Signals`: first-iteration mocked audit datasets that define the next
  telemetry the dev agent should emit
- `Metric Dictionary`: explanation of what each live and mocked metric means
  and why it matters for auditing the MCP stack and agent behavior

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

The `Refresh From Azure Agent` button in the dashboard dispatches an external
observatory script at `scripts/refresh_from_azure_agent.py`, which then calls
the shared workspace runner under `../agent/scripts/run_daily_summary.py`.
In the provided Docker Compose setup, the API container mounts `../agent`,
mounts `./scripts`, and keeps `AI_Tracking` writable specifically so this
refresh path can update tracking files before the observatory re-syncs them.

You can also run the refresh script manually:

```bash
poetry run python scripts/refresh_from_azure_agent.py --source manual-refresh
```

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
- LangGraph runtime CLIs can now emit minimal execution telemetry into `AI_Tracking/Metrics/ai-usage-log.md`; the observatory parses these `runtime:*` entries and exposes flow/status usage without requiring a new transport or schema.
- The Operations Overview now highlights runtime flow distribution, final status distribution, and recent runtime executions directly from those `runtime:*` usage events.
- The audit datasets are intentionally mocked in the first iteration so the
  observatory can document the desired MCP and agent telemetry before the live
  emitters are wired in.
- The folder is scaffolded to live as its own repository. Wire it into the
  parent repository as a formal git submodule once the remote repository URL is
  defined.
- The Docker image installs dependencies through Poetry and runs both app
  processes via `poetry run`.
