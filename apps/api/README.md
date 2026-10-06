# LETS API

FastAPI backend for LETS Video Analyzer. Contract: [`docs/api-contract.md`](../../docs/api-contract.md).

## Setup (Windows PowerShell)

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Run

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/v1/health

## Checks

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy app
```

## Configuration

Environment variables, prefixed `LETS_` (or a `.env` file in `apps/api`):

| Variable | Default |
| --- | --- |
| `LETS_CORS_ORIGINS` | `["http://localhost:3000","http://127.0.0.1:3000"]` (JSON list) |
| `LETS_DATA_DIR` | `apps/api/data` |
| `LETS_DATABASE_URL` | SQLite file in the data dir |
| `LETS_MAX_UPLOAD_BYTES` | 2 GB |

## Database

SQLite by default. Migrations run automatically on startup. After changing [app/models.py](app/models.py):

```powershell
.\.venv\Scripts\python -m alembic revision --autogenerate -m "describe change"
```
