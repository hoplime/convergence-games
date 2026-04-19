---
title: Fly.io hosting migration
created: 2026-04-19
status: in-progress
---

# Fly.io hosting migration

## Context

Previously hosted on Azure App Service + Azure DB. Too expensive year-round for an app that's low-traffic most of the year but spikes to 200+ concurrent users during one event weekend. Database moved to Neon (Sydney). Need cheap container hosting in NZ/Sydney with scale-to-zero.

Decision: Fly.io (Sydney). Azure Container Apps as fallback if issues arise.

## Requirements

- `GET /health` endpoint returns 200, no auth required, outside frontend router
- Gunicorn worker count configurable via `WEB_CONCURRENCY` env var (not hardcoded)
- `fly.toml` configured for Sydney region, scale-to-zero, health checks
- Azure Blob Storage credentials documented for non-Azure hosting

## Technical Design

### Health check endpoint

New standalone route handler at `convergence_games/app/routers/health.py`. Uses `@get` decorator directly (not a Controller) — registered in `convergence_games/app/routers/__init__.py` alongside the existing routers. Lives outside the frontend router so it skips the `before_request_handler` auth/profile redirect hook.

Returns `{"status": "ok"}` with 200. No DB check — this is a liveness probe, not a readiness probe. Keeps health checks fast and decoupled from DB latency.

### Configurable worker count

Gunicorn natively reads `WEB_CONCURRENCY` env var to set worker count. Remove `-w 4` from the CMD in `Dockerfile` (both default and azure stages). Deployments set `WEB_CONCURRENCY` in their environment config. Without it, gunicorn defaults to 1 worker — acceptable for dev, and prod always sets it explicitly.

### Fly.io config

`fly.toml` at project root. Key settings:
- `primary_region = "syd"` — Sydney
- `auto_stop_machines = "stop"` + `min_machines_running = 0` — scale to zero when idle
- Health check against `/health`
- `shared-cpu-1x` / 512MB for year-round idle — scale up manually before event weekend

The existing Dockerfile multi-stage build works with `fly deploy`. The `--mount=type=secret,id=npmrc` build secret passes via `fly deploy --build-secret npmrc=<path>`.

### Azure Blob credentials

`BlobImageLoader` (`convergence_games/services/image/blob_image_loader.py:29`) uses `DefaultAzureCredential`. Outside Azure, the `EnvironmentCredential` in its chain needs `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`. No code changes — just secrets config on Fly.

## Implementation Plan

### Phase 1: Health check endpoint

- [x] **Create health check route** (`convergence_games/app/routers/health.py`)
  - `@get("/health", include_in_schema=False)` async handler returning `Response(content={"status": "ok"}, status_code=200)`
- [x] **Register route** (`convergence_games/app/routers/__init__.py`)
  - Import `health_check` from `.health`, add to `routers` list

#### Phase 1 verification

- [x] `basedpyright` — no new errors
- [x] `ruff check` — no new errors
- [x] `curl http://localhost:8000/health` returns `{"status": "ok"}`

### Phase 2: Configurable worker count

- [x] **Remove hardcoded `-w 4`** (`Dockerfile`)
  - Line 68 (default stage CMD): remove `"-w", "4"` from the JSON array
  - Line 76 (azure stage CMD): same change

#### Phase 2 verification

- [ ] Docker builds successfully: `docker build --target default -t test .` (or just confirm syntax is valid)
- [ ] With `WEB_CONCURRENCY=2`, gunicorn logs show 2 workers on startup

### Phase 3: Fly.io config

- [x] **Create `fly.toml`** (project root)
  - App name, Sydney region, internal port 8000, HTTPS forced
  - Scale-to-zero config: `auto_stop_machines = "stop"`, `auto_start_machines = true`, `min_machines_running = 0`
  - HTTP health check on `/health` every 30s
  - VM size: `shared-cpu-1x`, 512MB

#### Phase 3 verification

- [ ] `fly deploy --remote-only --build-secret npmrc=<path>` builds and deploys
- [ ] `fly status` shows machine running in syd
- [ ] Site loads at Fly.io URL
- [ ] Health check passes: `curl https://<app>.fly.dev/health`

### Phase 4: Azure Blob credentials (manual, no code)

- [ ] Create Azure AD app registration / service principal with `Storage Blob Data Contributor` on the storage account
- [ ] Set Fly secrets: `fly secrets set AZURE_TENANT_ID=... AZURE_CLIENT_ID=... AZURE_CLIENT_SECRET=...`
- [ ] Verify image upload/retrieval works on deployed app

## Acceptance Criteria

- [ ] Type checking passes (`basedpyright`)
- [ ] Linting passes (`ruff check`)
- [ ] Dev server starts without errors
- [ ] `GET /health` returns 200 with `{"status": "ok"}`
- [ ] Gunicorn worker count controlled by `WEB_CONCURRENCY` env var
- [ ] App deploys to Fly.io Sydney and serves traffic
- [ ] Images load correctly (Azure Blob credentials working)

## Notes

- Event weekend scaling: `fly scale vm performance-2x --memory 4096` + `WEB_CONCURRENCY=4` before event, scale back after
- Fly.io free tier covers 3 shared VMs — idle cost should be ~$0/mo
- Azure Container Apps is the fallback if Fly.io has issues (familiar from work)
- SSH/entrypoint cleanup in Dockerfile default stage deferred — not causing issues
