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
| `LETS_EXTRACT_COLOR` | `true` (name each vehicle's color while analyzing) |
| `OPENAI_API_KEY` | empty = helmet check off (put it in `apps/api/.env`, never commit it) |
| `LETS_VISION_MODEL` | `gpt-4o-mini` (model for the helmet check) |
| `LETS_HELMET_MAX_CALLS` | `150` (most image calls one video can make) |
| `LETS_SEARCH_FPS` / `LETS_SEARCH_CONF` | `2.0` / `0.15` (open-vocabulary search) |

## Attributes and open-vocabulary search

- **Color** (cars, trucks, buses, motorcycles): worked out locally from a few crops per vehicle, no
  model or API. Eight names: white, black, gray, red, orange, yellow, green, blue. Silver counts as
  gray. Judged by eye on one clip; dark navy can read black and the odd maroon car reads gray.
- **Helmet** (people): an OpenAI vision model looks at 2 crops per person. It only runs when
  `OPENAI_API_KEY` is set, costs roughly cents per video, and is capped by `LETS_HELMET_MAX_CALLS`.
  People it cannot judge are reported as such, never guessed. Without a key the reply says the
  check is unavailable and counts everyone.
- **Anything else** ("trees", "traffic lights"): YOLO-World searches the video for that word once,
  in the background (about 17 s for 85 s of video on an RTX 4050), then answers from the result.
  Counts are rough and the reply says so. Run `python ml/tools/check_gpu.py --world` once to
  download its weights.
- Videos analyzed before an extractor was turned on have no such attributes; use the re-run button
  on the video to analyze it again.

## Database

SQLite by default. Migrations run automatically on startup. After changing [app/models.py](app/models.py):

```powershell
.\.venv\Scripts\python -m alembic revision --autogenerate -m "describe change"
```
