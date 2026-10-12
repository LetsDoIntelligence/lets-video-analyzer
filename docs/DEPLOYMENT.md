# Deploying LETS Video Analyzer

Path prefix: `/videoanalyzer` · web `127.0.0.1:3045` · API `127.0.0.1:8045` (both unused in the existing nginx registry).

## 1. Server

```bash
cd /var/www/deploy            # same place as lets-sports
git clone <repo-url> lets-video-analyzer && cd lets-video-analyzer
docker compose -f docker-compose.prod.yml up -d --build
curl -s http://127.0.0.1:8045/v1/health
curl -sI http://127.0.0.1:3045/videoanalyzer
```

Uploads + SQLite live in the `lets-data` volume. Update: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.

## 2. nginx

Paste into the `server { listen 443 ... }` block of letsdointelligence.ai, **before** the
`location /` catch-all and the global image-regex block (the `^~` modifiers keep the global
`.png/.jpg` regex from stealing thumbnails and assets):

```nginx
    # ============== LETS VIDEO ANALYZER ==============
    # Docker stack: web 3045 (Next.js, basePath /videoanalyzer), api 8045 (FastAPI, routes under /v1).
    location = /videoanalyzer {
        return 301 /videoanalyzer/;
    }
    # API: /videoanalyzer/api/x -> /v1/x. Large uploads, SSE job events, video range requests.
    location ^~ /videoanalyzer/api/ {
        rewrite ^/videoanalyzer/api/(.*) /v1/$1 break;
        proxy_pass http://127.0.0.1:8045;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 2100M;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 900s;
        proxy_send_timeout 900s;
    }
    # Frontend (prefix is passed through; Next.js is built with basePath /videoanalyzer)
    location ^~ /videoanalyzer/ {
        proxy_pass http://127.0.0.1:3045;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
```

Then `sudo nginx -t && sudo systemctl reload nginx` → https://letsdointelligence.ai/videoanalyzer/

## Notes
- `NEXT_PUBLIC_*` and the base path are baked in at build time; changing them needs `--build`.
- The API image is `apps/api/Dockerfile.gpu` (PyTorch cu126 + Ultralytics, `yolo11s.pt` baked in), so uploads are analyzed on the GPU exactly like local dev. First build is large (~8 GB) and slow.
- Host prerequisite: NVIDIA driver + NVIDIA Container Toolkit. Verify with
  `docker exec lets-video-analyzer-api python -c "import torch;print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` (expect `True`, RTX 6000 Ada).
  If it prints False: `sudo apt install nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`, then recreate the stack.
- Analysis state/progress shows in the UI after upload; check `docker logs -f lets-video-analyzer-api` if it stays on `failed`.
