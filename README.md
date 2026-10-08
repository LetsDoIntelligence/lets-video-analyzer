# LETS Video Analyzer

Ask natural-language questions about a video ("how many cars between 3:00 and 6:00?") and get
answers as text, tables and charts. Backed by detection/tracking models and an LLM query planner.

## Structure
```
apps/web   Next.js 16 + TypeScript + Tailwind v4 frontend
apps/api   FastAPI backend (uploads, probe/thumbnail, jobs, simulated /v1/analyze)
ml/        Detection / tracking / evaluation pipelines
docs/      Architecture notes and API contract
```

## Develop

### Docker (API + web together)
```
docker compose up --build     # web http://localhost:3000, API http://localhost:8000
```
Uploads and the SQLite DB persist in the `lets-data` volume. The API URL is baked into the web
image at build time (`NEXT_PUBLIC_API_URL` build arg in `docker-compose.yml`). CI
(`.github/workflows/ci.yml`) runs lint, typecheck, unit tests and e2e for both apps.


### Frontend only (mock data, no backend)
```
cd apps/web
npm run dev        # http://localhost:3000
```

### Frontend + real API
```
# terminal 1 - API on :8000 (see apps/api/README.md for setup)
cd apps/api
conda activate lets-video; lets-api          # http://localhost:8000 (auto-reload)

# terminal 2 - web; create apps/web/.env.local with:
#   NEXT_PUBLIC_USE_MOCKS=false
#   NEXT_PUBLIC_API_URL=http://localhost:8000
cd apps/web
npm run dev
```
Restart `npm run dev` after changing any `NEXT_PUBLIC_*` variable.
After an upload the API starts analysing the video in the background (YOLO11 detection +
ByteTrack tracking, set up per ml/README.md). The video panel shows `Analyzing 42%` and then
`Analyzed · N objects`. The result is cached per video and rebuilt only when the settings change
(or via the re-analyze button). Answers to questions are still simulated until P3-6.

### Checks
```
cd apps/web
npm run lint; npm run typecheck; npm run test
npm run test:e2e                      # mock-mode smoke tests (dev server must use mocks)
npm run gen:api                       # regenerate src/lib/api/generated.ts from apps/api/openapi.json

# full-stack e2e: API on :8000, web built with NEXT_PUBLIC_USE_MOCKS=false and served on :3100
$env:E2E_STACK="1"; $env:E2E_BASE_URL="http://localhost:3100"; npm run test:e2e:stack

cd apps/api
.\.venv\Scripts\python -m pytest; ruff check; mypy app
.\.venv\Scripts\python scripts/export_openapi.py   # then npm run gen:api in apps/web
```
