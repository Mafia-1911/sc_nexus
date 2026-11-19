# Deploying Supply Chain Nexus (ShipperFast)

There are two ways to run the project:
- **local demo**: one machine, Docker, about 10 minutes;
- **hosted demo**: free tiers, a public URL.

Decisions behind the hosted setup: A-119 (Neon), A-120 (Render + Vercel), A-121 (cloud refresh).

## 0. How it fits together

```
           ┌──────────── your machine (Docker) ────────────┐
           │ db (Postgres+PostGIS+pgvector) ◄─ migrate,     │   local demo: everything here
           │ api :8000 ◄─ web :3000      worker, seed       │   (make demo)
           └───────────────┬───────────────────────────────┘
       deploy_db.sh (once) │      cloud_refresh.sh (hourly / 6-hourly) or make worker-cloud
                           ▼
 Vercel (web, Next.js) ──API_TOKEN──► Render (api, FastAPI, free 512 MB) ──► Neon (Postgres, free 0.5 GB)
   logins: AUTH_DATABASE_URL ─────────────────────────────────────────────────┘
```

- **Neon** holds the data. The deployed API is read-only for the data pipelines; nothing on Render fetches feeds.
- **Render** runs the API image (`Dockerfile`) from `render.yaml`. Every start runs `alembic upgrade head`, so new migrations reach Neon on deploy. It sleeps after 15 minutes idle, and the first request after that takes about 30 to 60 seconds.
- **Vercel** serves `apps/web`. Its server-side code calls Render with `API_TOKEN`; the browser never sees keys.
- **Data freshness.** Your machine pushes fresh data into Neon in one of two ways:
  - `scripts/cloud_refresh.sh` on a timer: a short run, then it disconnects so Neon's free compute can suspend.
  - `make worker-cloud`: the full worker, always on. It uses more Neon compute hours.

## 1. The `.env` file (the team's `env.bin`)

Save the team file as **`.env` in the repo root**, next to `Makefile`:

```bash
cp /path/to/env.bin .env
```

`.env` is git-ignored. Never commit it, paste it into chat, or send it to the browser.

**What it holds.** `packages/core/src/cportal_core/settings.py` accepts both spellings, so the team names work:

| Purpose | Name(s) in the team file | Needed for |
|---|---|---|
| Neon pooled URL | `DATABASE_URL` | Vercel logins (`deploy_vercel.sh`) |
| Neon direct URL | `DATABASE_URL_UNPOOLED` | `deploy_db.sh`, `cloud_refresh.sh`, `cloud_tariffs.sh`, `worker-cloud`, Render's `DATABASE_URL` |
| API shared token | `API_TOKEN` | Render and Vercel |
| Web session secret | `AUTH_SECRET` (generated once if missing) | Vercel |
| Render URL | `RENDER_API_URL` | Vercel |
| Vercel deploy token | `VERCEL_TOKEN` | `deploy_vercel.sh` |
| Feeds and models (optional; missing means replay) | `AIS_STREAM_APIKEY`, `GLOBAL_FISHING_WATCH_GFW_ACCESS_TOKEN`, `UN_COMTRADE_APIKEY`, `OPEN_FDA_APIKEY`, `NASA_FIRMS_MAPKEY`, `NASA_EARTHDATA_TOKEN`, `RELIEFWEB_APPNAME`, `HEIGIT_KEY`, `TOM_TOM_APIKEY`, `MAPBOX_API`, `DATADOCKED_APIKEY`, `ROBOFLOW_APIKEY`, `KAGGLE_APIKEY` | AIS map, C2 news, C3, C4, C5, vessel info |
| Not read by the code | `PG*`, `POSTGRES_*`, `HF_TOKEN` (added by the Vercel–Neon integration) | — |

**The Tariff Monitor needs no keys.** Its sources (DS-TRADE-04 to 08) are `auth: none`.

> **Watch out:** the team `.env` points `DATABASE_URL` at **Neon**.
> - `make` targets force the local database (`Makefile` line 8), and so does Docker compose.
> - A bare `uv run …` outside `make` reads `.env` and writes to the **deployed** database.

## 2. Local demo (Docker)

Prerequisites: Docker with Compose v2 and `make`. You don't need `uv` or Node for this path.

```bash
make demo
```

This:
1. builds the `cportal-app` and web images;
2. starts db, migrate, api, worker and web;
3. seeds the database with the reference replay, the synthetic scenarios and the C6 tariff matrix;
4. restarts the worker.

Open http://127.0.0.1:3000.

Smoke checks:

```bash
curl -s http://127.0.0.1:8000/health
```

```bash
curl -s -H "Authorization: Bearer $(grep -E '^"?API_TOKEN"?=' .env | cut -d= -f2- | tr -d '"')" "http://127.0.0.1:8000/api/v1/tariffs/overview" | head -c 300
```

The offline, timed golden path, which needs no live feeds and no LLM:

```bash
make golden
```

Stop everything (the data stays in the `pgdata` volume):

```bash
make down
```

When `.env` sets `API_TOKEN`, the API answers only with that bearer token (`/health` is exempt); the web server sends it for you.

For the laptop path without Docker for the app, see `handoff.md` §6.

## 3. Hosted demo, first time

Do these steps in order, from the repo root, with `.env` in place and Docker running.

1. **Build and seed locally.**
   ```bash
   make demo
   ```
2. **Copy the database to Neon, once.**
   ```bash
   scripts/deploy_db.sh
   ```
   - It prints the local size first; Neon's free tier holds 0.5 GB.
   - If Neon already has the schema, it does nothing. Drop the database in the Neon console first if you need to copy it again.
3. **Load the Tariff Monitor into Neon.** This is needed if Neon was copied before C6 existed, and harmless otherwise. It applies migrations, replays the tariff samples and builds the matrix.
   ```bash
   make cloud-tariffs
   ```
4. **API on Render.**
   1. In the Render dashboard choose **New → Blueprint** and select this GitHub repo. `render.yaml` targets branch `m3-c1`.
   2. Paste these env vars:
      - `DATABASE_URL`: the Neon **direct** URL, from `DATABASE_URL_UNPOOLED`;
      - `API_TOKEN`;
      - `MAPBOX_API`, optional;
      - `DATADOCKED_APIKEY`, optional.
   3. Wait for `/health` to go green, then put the service URL in `.env` as `RENDER_API_URL`.
   - **The repo moved** to `Rafee-M/sc_nexus`. Reconnect the Render service (Settings → Repository) to the new repo, or auto-deploy stops.
5. **Web on Vercel.**
   ```bash
   scripts/deploy_vercel.sh
   ```
   - It links the Vercel project `cportal`, sets `API_URL`, `API_TOKEN`, `AUTH_SECRET`, `AUTH_DATABASE_URL`, `NEXT_PUBLIC_WS_URL=off` and `NEXT_PUBLIC_MAP_SOURCE=online`, then deploys to production.
   - It needs Node (`npx`).
6. **Keep the data fresh.** Choose one:
   - Hourly timer, until the next reboot:
     ```bash
     make cloud-refresh-timer
     ```
     It runs a CPA poll every hour. Every 6 hours it also refreshes the yards, the live feeds (news, hazards, tariffs), the C2 events, the **C6 matrix** and Nexus.
   - Always-on worker against Neon:
     ```bash
     make worker-cloud
     ```
     Switch it back with `make worker-local`.
7. **Smoke-test the public site.**
   - Log in.
   - Check that the Control Tower loads.
   - Check `/tariffs`: the matrix shows LIVE or REPLAY badges, and the news tab loads.
   - Check that `/routes` shows the border-duty card, that the `/network` node drawer shows tariffs, and that `/radar` shows the tariff check.

## 4. Updating a deployed demo

| You changed | Do |
|---|---|
| API or worker code | Push to `m3-c1`; Render auto-deploys. Rebuild the local image (`make up`) so the refresh scripts run the new code. |
| A migration | Push. Render runs `alembic upgrade head` on start. If it adds C6 tables or columns, run `make cloud-tariffs`. |
| Web code | `scripts/deploy_vercel.sh` (or push, if the Vercel Git integration is on). |
| Tariff parsers or config | Rebuild the image, run `make cloud-tariffs`, and bump `PARSER_VERSION` if parser output changed (no phantom changes). |
| Secrets | Edit `.env`, then re-run `deploy_vercel.sh` or update Render's env vars. |

## 5. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| First page load is slow or times out | Render is waking up; wait about 60 s and reload. |
| `/tariffs` is empty on the hosted site | Neon lacks C6 data. Run `make cloud-tariffs`. |
| `DATABASE_URL_UNPOOLED missing in .env` | `.env` is not in the repo root, or it's missing that name. |
| Local `uv run …` changed the live site | You ran outside `make` with the team `.env`. Use `make` targets or set `DATABASE_URL` to the local database. |
| `cportal-app:latest` not found | Build the image with `make up` (or `docker compose build`). |
| Neon "compute time exceeded" | Stop `worker-cloud` and use the timer instead. |
| Push or auto-deploy stopped after the repo move | Reconnect Render/Vercel to `Rafee-M/sc_nexus`, and set the git remote: `git remote set-url origin https://github.com/Rafee-M/sc_nexus.git`. |

## 6. Can a Claude cloud session run and verify it?

It can run part of it:

| What | In a Claude cloud session |
|---|---|
| Python tests, lint and types (`make test`, `make lint`, `make type`) | **Yes.** `uv` is installed. Database tests need Postgres, and `make db-local` installs a user-level one (no Docker). |
| Run the app (`make db-local`, `make seed`, `make api`, `make web`) and Playwright e2e with screenshots | **Yes.** Chromium is pre-installed. This is how the Tariff Monitor UI was verified. |
| Real tariff and news feeds | Only if the environment's network allows those hosts. Otherwise replay mode uses the committed samples. |
| `make demo` (Docker) | **Yes, with a workaround** (verified 2026-11-19). The daemon is installed but stopped: start it with `dockerd &`. Builds cannot reach the network proxy or trust its certificate, and Debian mirrors use plain HTTP, which the proxy refuses. So build from local copies of the three Dockerfiles that copy `/root/.ccr/ca-bundle.crt` in, switch apt to HTTPS and pass `--network host --build-context ccr=/root/.ccr --build-arg HTTPS_PROXY=…`. Then `docker compose up -d --no-build` with `CPORTAL_LIVE=0`, because containers cannot reach the proxy either (replay only). If Docker Hub answers 429, add `--pull=false`. The C3 road graph needs `make road-graph` (the OSM extract in `data/raw/DS-GEO-01/`). |
| Playwright in the session | The project pins a newer Playwright than the pre-installed browser. Use a local config that sets `launchOptions.executablePath: "/opt/pw-browsers/chromium"`, and run with `--trace off`. Map tiles need the internet, so the live-map idle check can time out. |
| Deploy to Neon, Render or Vercel | Needs the keys in that session (environment secrets, never chat) and network access to those hosts. Render's dashboard steps need a person. The refresh scripts need Docker with network access, so run them on your machine. |
| Check the deployed site | Yes, with Playwright, if the network allows the Vercel and Render hosts. |
