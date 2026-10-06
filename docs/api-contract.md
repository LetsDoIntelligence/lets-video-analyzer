# API contract — `POST /v1/analyze`

Source of truth: [`apps/web/src/lib/api/schemas.ts`](../apps/web/src/lib/api/schemas.ts) (Zod).
The Phase 2 FastAPI backend must match it.

## Request

`Content-Type: application/json`

```json
{
  "question": "how many cars passed?",
  "scope": {
    "videoId": "sample-1",
    "videoName": "Synthetic traffic",
    "start": 180,
    "end": 360,
    "duration": 600,
    "label": "3:00 – 6:00"
  }
}
```

`start`/`end` are seconds; the answer must only consider that window.

## Response

`Content-Type: text/event-stream`. Each event is a single `data:` line holding JSON, followed by a blank line.

| `type`   | Payload                       | Notes                                   |
| -------- | ----------------------------- | --------------------------------------- |
| `text`   | `{ "chunk": string }`         | Markdown-ish (`**bold**`). Sent many times; concatenated. |
| `blocks` | `{ "blocks": ReplyBlock[] }`  | Sent once, after the text.              |
| `error`  | `{ "message": string }`       | Terminal. Shown to the user verbatim.   |

```
data: {"type":"text","chunk":"I counted **12** cars. "}

data: {"type":"blocks","blocks":[{"type":"stat","label":"Cars","value":"12"}]}
```

## Reply blocks

Discriminated on `type`: `stat`, `chart`, `table`, `timestamps`. See `replyBlockSchema` for exact fields.

## Errors

- Non-2xx status → the UI shows "The analysis service returned an error (status)."
- Invalid JSON or schema mismatch → "unexpected response". Keep the contract strict.

## Frontend config

| Variable                   | Default                 | Meaning                          |
| -------------------------- | ----------------------- | -------------------------------- |
| `NEXT_PUBLIC_USE_MOCKS`    | `true`                  | Use the in-browser fake analyzer |
| `NEXT_PUBLIC_API_URL`      | `http://localhost:8000` | Backend base URL                 |

## Videos and jobs (backend, Phase 2)

Full, always-current reference: `GET /docs` on the running API (OpenAPI). JSON is camelCase.

| Method & path | Purpose |
| --- | --- |
| `POST /v1/videos` | Upload (multipart field `file`). 201 with the video; 415/413/400/422 on bad input. |
| `GET /v1/videos`, `GET /v1/videos/{id}` | List (newest first) / fetch. Includes `durationSec`, `fps`, `width`, `height`, `codec`, `src`, `thumbnailSrc`. |
| `DELETE /v1/videos/{id}` | Remove the video, its files and jobs (running jobs are cancelled). 204. |
| `GET /v1/videos/{id}/file` | The video; supports HTTP Range. |
| `GET /v1/videos/{id}/thumbnail` | JPEG thumbnail. |
| `POST /v1/videos/{id}/jobs` | Body `{"kind": "indexing"}`. 202 new job, or 200 with the already-active job of that kind. |
| `GET /v1/videos/{id}/jobs`, `GET /v1/jobs/{id}` | Job status: `queued`, `running`, `succeeded`, `failed`, `cancelled`; `progress` 0-1; `error`. |
| `POST /v1/jobs/{id}/cancel` | 202, or 409 if the job already finished. |
| `GET /v1/jobs/{id}/events` | SSE: a full job object on connect and on every change, closing once the job ends. |

The `indexing` job is currently a placeholder that only reports progress; Phase 3 makes it run detection and tracking.
