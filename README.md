# KL Observatory

Operational observatory for the KwikLedgers agent stack.

This project reads the existing workspace tracking outputs under
`../AI_Tracking`, persists snapshots into Postgres through a small FastAPI
service, and exposes the operational view through Streamlit.

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

Services:

- Streamlit: `http://localhost:8501`
- FastAPI: `http://localhost:8000`
- Postgres: `localhost:5432`

## Local Python Run

```bash
poetry install
poetry run uvicorn kl_observatory.api:app --host 0.0.0.0 --port 8000
poetry run streamlit run src/kl_observatory/dashboard.py
```

## Notes

- The dashboard can fall back to direct file reads if the API is unavailable.
- The folder is scaffolded to live as its own repository. Wire it into the
  parent repository as a formal git submodule once the remote repository URL is
  defined.
- The Docker image installs dependencies through Poetry and runs both app
  processes via `poetry run`.
