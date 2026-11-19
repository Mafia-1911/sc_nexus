# Handoff: Supply Chain Nexus (Cportal, brand "ShipperFast")

Read this first in any new session. It tells you what the project is, where each thing lives, how to change the UI, how to make a change that crosses layers, and how to build, test and deploy. The rules in `AGENTS.md` still win where they conflict with this file.

Updated 2026-11-19. Repo: https://github.com/Rafee-M/sc_nexus (moved from UpperPanda1/sc_nexus), branch `m3-c1`.

**Contents:** [1 What it is](#1-what-it-is-30-seconds) · [2 Repo map](#2-repo-map-what-lives-where) · [3 Tariff Monitor](#3-the-tariff-monitor-c6-as-built) · [4 Change the UI](#4-how-to-modify-the-ui) · [5 Cross-layer change](#5-how-to-make-an-integrated-cross-layer-change) · [6 Build, run, test, keys](#6-build-run-and-test) · [7 Deploy](#7-deploy-for-a-hosted-demo-free-tiers-a-119-and-a-120) · [8 Gotchas](#8-gotchas-learned-the-hard-way) · [9 Start prompt](#9-start-prompt-for-a-new-session-copy-and-paste)

## 1. What it is (30 seconds)

A supply-chain resilience platform for Bangladesh's **Chattogram → Dhaka** corridor, for garment (RMG) and pharma shippers. It turns ships, ports, suppliers, trade news, factory quality and **tariffs** into decisions.

| ID | Capability | Package | Page |
|---|---|---|---|
| C1 | Supplier risk graph | `packages/c1_supplier_graph` (`cportal_c1`) | `/network` |
| C2 | Trade-news intelligence (and the tariff news signal) | `packages/c2_trade_news` (`cportal_c2`) | `/radar` |
| C3 | Routing optimisation | `packages/c3_routing` (`cportal_c3`) | `/routes` |
| C4 | Port dwell prediction | `packages/c4_port_dwell` (`cportal_c4`) | `/ports` |
| C5 | Defect intelligence | `packages/c5_defect_intel` (`cportal_c5`) | `/quality` |
| C6 | **Tariff Monitor** (added 2026-11-18, ADR-021) | `packages/c6_tariffs` (`cportal_c6`) | `/tariffs` |
| Nexus | Scenarios, evidence fusion, recommendations, alerts | `packages/nexus` (`cportal_nexus`) | `/scenarios`, Control Tower `/` |

The Data & Models page is `/data`. Current state, open work and blockers are in `docs/STATUS.md`, which is always the most recent truth.

## 2. Repo map: what lives where

```
AGENTS.md              standing brief (rules, decisions D-xx, gates). CLAUDE.md imports it.
handoff.md             this file
Makefile               every entry point: `make help`
docker-compose.yml     db, migrate, api, worker, web, seed (profile)
render.yaml            API on Render (runs alembic upgrade head on start)
deploy/worker-neon.yml compose override: local worker writing to Neon
scripts/               deploy_db.sh (local → Neon), deploy_vercel.sh, cloud_refresh.sh, db-local.sh
config/
  sources.yaml         source registry DS-* (licence, mode, rate limits)
  tariffs/             watchlist, countries, us_programs, us_exemption_categories, eu_preferences, feeds
  c2/lexicon.yaml      news event lexicon (incl. trade policy)
  industry_packs/      garment.yaml, pharma.yaml (SKUs, HS6)
data/raw/DS-*/         committed probe samples (replay mode reads these)
db/alembic/versions/   migrations
packages/
  core/                ORM models (models/*.py), Pydantic records (schemas/records.py), settings, outbox
  connectors/          sources/ds_*.py (one per DS-ID), parsers/*.py, live.py (HTTP), loader
  sim/                 synthetic world (fictional companies, is_synthetic=true)
  c1…c6, nexus/        capability packages: each has service.py (public API), store.py, cli.py, tests/
apps/
  api/                 FastAPI; routers/<capability>.py are thin wrappers over cportal_cN.service
  worker/              jobs + schedule + outbox dispatcher (c6.py = tariff refresh)
  web/                 Next.js 16 App Router
    app/(app)/<page>/  page.tsx (server) + actions.ts (server actions)
    components/<page>/ page components; components/ui/ shared primitives; data-badge.tsx
    lib/cN.ts          typed fetchers and formatters per capability; lib/api/types.ts (generated)
    e2e/*.spec.ts      Playwright + axe
docs/
  STATUS.md            done / in progress / next / blockers (update every session)
  DECISIONS.md         assumptions A-xx and answered questions Q-xx
  adr/                 ADR-001…021
  brief/               the spec (read-only): 01-product … 08-nexus-layer, capabilities/C*.md
  tariffs/             BACKEND.md, LIVE_FEEDS.md, UI_PLAN.md (+ .docx)
  api/openapi.json     generated API contract (63 paths)
  data-sources/        one card per DS-ID; model-cards/; ERD.md; GOLDEN_PATH.md; VIDEO_SCRIPT.md; USER_TASKS.md
```

Boundaries are enforced by import-linter (`pyproject.toml`):
- `packages/cN_*` import only `cportal_core`.
- Capabilities talk through DB tables, outbox events or another package's `service.py` (called from Nexus, the API or the worker).
- Example: C2 writes `tariff_news`, and C6 reads it. C6 never imports C2.

## 3. The Tariff Monitor (C6), as built

**Sources**

| ID | Source | Status |
|---|---|---|
| DS-TRADE-05 | USITC HTS | live |
| DS-TRADE-07 | UK Trade Tariff | live |
| DS-TRADE-04 | WITS (annual MFN; Japan, Canada, EU fallback) | live |
| DS-TRADE-06 | Federal Register notices | live |
| DS-TRADE-08 | EU preference table | hand-kept YAML |

The missing feeds and their to-dos are in `docs/tariffs/LIVE_FEEDS.md`; EU TARIC comes first.

**Pipeline.** The connector is ingested, the outbox emits `source.ingested`, and the worker runs `c6.refresh`. That job also runs every 6 h. `cportal_c6.store.refresh` does three things:
1. **mark current:** flags the latest snapshot per source and scope.
2. **detect changes:** diffs consecutive snapshots into `tariff_change` and emits `tariff.changed`.
3. **compute rates:** precomputes `tariff_effective_rate` for 5 markets × 22 products × 7 origins (770 cells, about 0.3 s).

**Engine rules** (`rates.py`): base MFN, then the best valid preference, then surcharges.
- Values are **never guessed**. Stacked surcharges, specific or compound duties, staged FTA rates and category exemptions become *unresolved*. The UI shows them hatched as "≥ floor" or "up to".
- Japan and Canada have no preference data, so their rates are ceilings (`is_ceiling`). The UI writes them as "≤".
- Snapshots carry the parser version (`c6-parsers-2`). Diffs run only between snapshots with the same non-empty version, so a parser upgrade never creates phantom changes.

**News.** C2 reads a tariff signal from every real article and writes stories to `tariff_news`. The code is `cportal_c2/tariff.py` and `tariff_news.py`.
- Each story records direction, markets, origins, rates, effective date and the quoted words.
- Trade-policy events get the subtype `tariff_raise|cut|exempt|unknown`. Cuts and exemptions raise no alert.
- C6 marks a story `confirmed` when a matching `tariff_change` exists. The UI then says "in the schedule" rather than "announced".

**API** (`/api/v1/tariffs`, envelope `{data, meta}`, `meta.mode` drives the badge):
- `overview`, `matrix`, `products/{hs6}`, `changes`, `notices`, `origins/{iso3}`, `news`.
- The Control Tower daily brief (`routers/brief.py`) cites tariff lines.

**UI**

| Where | What |
|---|---|
| `/tariffs` | Workbench: matrix heatmap (markets or origins view), detail card, activity tabs for changes, news and notices. Deep link `?hs6=&market=&origin=`. |
| `/routes` | Border-duty card (`components/routes/border-duty.tsx`) |
| `/network` | Node drawer tariffs (`components/network/node-tariffs.tsx`). Deep link `?node=`. |
| `/radar` | Event drawer tariff check (`components/radar/tariff-check.tsx`) |

The server actions are in `app/(app)/tariffs/actions.ts`, and the types and formatters in `lib/c6.ts`.

**CLI**

```bash
uv run c6 refresh
```

```bash
uv run c6 rate 610910 --market GBR --origin BGD
```

```bash
uv run c6 changes
```

**Full detail:** `docs/tariffs/BACKEND.md`, `UI_PLAN.md`, `LIVE_FEEDS.md`, ADR-021, and DECISIONS A-125…A-141 and Q-18…Q-26.

**Backend next steps** are listed in BACKEND.md §6:
1. LDC graduation scenario
2. Duty exposure on open orders
3. Rules-of-origin check from the BOM
4. "Ship before cut-off" recommendation
5. Section 301/232 ranges
6. EU TARIC

## 4. How to modify the UI

1. **Find the pattern first.** Open the nearest existing page and its components, and follow them. Shared pieces:
   - `components/ui/*`: Card, CardFooter, Badge (opaque `color-mix` fills for contrast), and the other primitives.
   - `components/data-badge.tsx`: the LIVE, REPLAY or SYNTHETIC badge. **Every data surface needs one** (hard rule 3).
   - `components/glossary.tsx` and `kpi-strip.tsx`.
   - `lib/utils.ts`: `cn`, `dhakaTime`.
   - Use the ui-consistency skills: finding-patterns → planning → implementing → verifying. For a small change on one page, use adjusting.
2. **Tokens, not hex.**
   - Colours, the depth ramp, radii and focus are CSS variables in `apps/web/app/globals.css`. The spec is `docs/brief/05-ui-design.md`.
   - Use classes like `bg-surface`, `text-muted`, `border-border` and `rounded-[var(--radius-control)]`.
   - Light and dark themes both come from the tokens.
3. **Data flow.**
   - The server `page.tsx` fetches through `lib/cN.ts` and passes plain props to client components.
   - Client interaction calls server actions in `actions.ts`. Never call the API from the browser; tokens and keys stay server side.
4. **When the API shape changes:**
   1. Run `make openapi`, which regenerates `docs/api/openapi.json`.
   2. Run `cd apps/web && npm run gen:api`, which regenerates `lib/api/types.ts`.
   3. Fix the types in `lib/cN.ts`.
5. **Cards on maps.** Info cards use the `data-reference` card pattern (see `components/routes/border-duty.tsx`). Deep links use search params, for example `/network?node=` and `/tariffs?hs6=`.
6. **Accessibility.**
   - Buttons need an `aria-label` when their text is not enough.
   - Tables need `scope` on their headers and an sr-only `caption`.
   - Never convey meaning by colour alone. The matrix uses text plus hatching.
   - axe runs in `e2e/a11y.spec.ts`; add new routes to its list, and to `sources.spec.ts` if the page shows sources.
7. **Verify in the browser:** 1280 px, light and dark. Run `make e2e`; screenshots go to `docs/screenshots`. Then run `make web-check` (tsc and lint).

## 5. How to make an integrated (cross-layer) change

Follow this order. Each step has its own tests.

1. **Source.** Add or adjust `config/sources.yaml`, save a raw sample under `data/raw/DS-*/`, and write a source card in `docs/data-sources/`. Probe first (D-08) and record the licence.
2. **Connector.**
   - Write the parser in `packages/connectors/.../parsers/` and the source module in `sources/ds_*.py`.
   - Test the parser against the real sample, and add a replay contract case.
3. **Core.**
   - Add the ORM model in `packages/core/.../models/`, the record in `schemas/records.py`, and a migration:
     ```bash
     make revision MSG="..."
     ```
   - **A new NOT NULL column on a filled table needs a `server_default`.** Add a migration test like `tests/test_c6_migration.py`.
   - Run `make erd`.
4. **Capability package.** Put the logic in pure functions with unit tests, `store.py` for the DB, and `service.py` as the public read API. Import only core.
5. **Worker.** Add the job in `apps/worker/.../cN.py`, the schedule, and outbox dispatch if it reacts to ingests. Test it in `apps/worker/tests`.
6. **API.** Add a thin router in `apps/api/.../routers/` with the `{data, meta}` envelope and `meta.mode` / `sources`. Write a contract test covering filters, 404/422 and the 300 ms p95 latency.
7. **Contract.** Run `make openapi` and `npm run gen:api`.
8. **Web.** Update `lib/cN.ts`, then the page, components and actions, then e2e and a11y.
9. **Cross-links.**
   - Nexus or brief hooks call another package's `service.py`, never its internals.
   - Example: C6 is cited in `routers/brief.py` and shown on `/routes`, `/network` and `/radar`.
10. **Docs.** Update STATUS.md, DECISIONS.md (A-xx), an ADR if the change is architectural, and the source or model card. Then run `make check`.

## 6. Build, run and test

**Prerequisites:** Docker, `uv`, Node 20+. Copy `.env.example` to `.env`; `make up` does this automatically.

**Keys and `.env`.** All secrets go in `.env` at the repo root. It is git-ignored and is never committed or printed.
- `packages/core/src/cportal_core/settings.py` accepts several spellings of each key, so both the `.env.example` names and the team's names work: `AISSTREAM_API_KEY` or `AIS_STREAM_APIKEY`, `GFW_API_TOKEN` or `GLOBAL_FISHING_WATCH_GFW_ACCESS_TOKEN`, and so on.
- **The Tariff Monitor needs no keys.** Every tariff source (DS-TRADE-04 to 08) is `auth: none` in `config/sources.yaml`.
- AIS (the live map) needs the aisstream key. C2 news, C3 calibration, the vessel info panel and others use optional keys; a missing key falls back to replay.
- The team `.env` sets `DATABASE_URL` to **Neon**, the deployed database.
  - The `make` targets override it with the local database (`Makefile` line 8), and so does compose.
  - A bare `uv run …` outside `make` reads `.env` and **writes to Neon**.
  - Locally, use the `make` targets, or prefix the command with `DATABASE_URL=postgresql+psycopg://cportal:cportal@localhost:5432/cportal`.

**Demo with Docker (recommended):**

```bash
make demo
```

This builds and starts db, migrate, api, worker and web. It then seeds the database: reference replay, synthetic scenarios and `c6 refresh`. Open http://127.0.0.1:3000.

To stop everything:

```bash
make down
```

**Laptop path, without Docker for the app.** Run each in its own terminal where noted:

```bash
make setup
```

```bash
make db-local
```

```bash
make seed
```

```bash
make api
```

```bash
make worker
```

```bash
make web-setup && make web
```

- `make setup` installs the uv workspace.
- `make db-local` starts a local Postgres with PostGIS and pgvector.
- `make seed` runs migrate, the replay, the scenarios and `c6 refresh`.
- `make api` serves on :8000, `make worker` runs the worker, and `make web` serves on :3000.

**Optional data:**
- `make road-graph` builds the C3 OSM road graph. It needs the extract described in `docs/USER_TASKS.md`.
- The C4 and C5 model weights and datasets are described in USER_TASKS.md and the model cards.

**Tests and checks:**

```bash
make test
```

```bash
make check
```

```bash
make e2e
```

- `make test` runs pytest on all packages; the database tests need Postgres up.
- `make check` runs lint, type checks, tests and web-check, which is everything CI runs.
- `make e2e` runs Playwright and axe against :3000, so the web server must be running.

**Golden path (offline, timed demo):**

```bash
make golden
```

```bash
make golden-walk
```

The script is in `docs/GOLDEN_PATH.md`, and the video plan in `docs/VIDEO_SCRIPT.md`.

**Live versus replay:** `CPORTAL_LIVE=0` replays the committed samples, and `CPORTAL_LLM=0` disables the LLM. Tariffs never use synthetic rows.

## 7. Deploy for a hosted demo (free tiers, A-119 and A-120)

**Full step-by-step guide: [`docs/DEPLOY.md`](docs/DEPLOY.md)**. It covers the `.env` / team `env.bin` placement, local and hosted setup, updates, troubleshooting, and what a Claude cloud session can run. The summary is below.

1. **Database on Neon.** Put Neon's direct URL in `.env` as `DATABASE_URL_UNPOOLED` (or `NEON_DATABASE_URL`), start the local stack and seed it, then run:
   ```bash
   scripts/deploy_db.sh
   ```
   It prints the size first; the free tier allows 0.5 GB.
2. **API on Render.** Use `render.yaml`. It runs `alembic upgrade head` on start, so new migrations apply on deploy. Set the env vars listed in `render.yaml` in the Render dashboard.
3. **Web on Vercel.** Put `VERCEL_TOKEN`, `API_TOKEN`, `RENDER_API_URL` and the pooled Neon URL as `DATABASE_URL` in `.env`, then run:
   ```bash
   scripts/deploy_vercel.sh
   ```
   It generates `AUTH_SECRET` once.
4. **Keep the data fresh.** Choose one:
   - `make worker-cloud` runs a local worker against Neon. It needs `DATABASE_URL_UNPOOLED`.
   - `make cloud-refresh-timer` runs `scripts/cloud_refresh.sh` hourly. CPA runs every hour; live feeds, C2 and Nexus every 6 h.
5. **After a tariff change, a migration or a fresh Neon copy, refresh the matrix on the target database.** Run:
   ```bash
   make cloud-tariffs
   ```
   This applies migrations, replays the tariff samples and builds the matrix in Neon. `cloud_refresh.sh` now also rebuilds the C6 matrix every 6 hours.
6. **Smoke test.** Open `/tariffs`, `/routes`, `/network` and `/radar` on the deployed site, and check that the badges and the LIVE/REPLAY mode are right.

Secrets live only in `.env`, never in git, logs or the browser. Values are never printed by the scripts.

## 8. Gotchas (learned the hard way)

| Gotcha | What to do |
|---|---|
| `LiveHttp` once dropped a URL's own query string | Fixed in `connectors/live.py`. Keep a test for any new query-string source. |
| Shadowed loop variables in `c2/store.py` stored real events as synthetic (A-136) | Watch for this when editing scenario loops. |
| Direction words in headlines were misread | They count only within 6 words of a tariff word. |
| Known C6 defects from the 2026-11-19 adversarial review | See `docs/tariffs/REVIEW_2026-11-19.md`; fix them before the demo. |
| Phantom tariff changes | Never diff snapshots across parser versions. Bump `PARSER_VERSION` when a parser's output changes. |
| Buyer SKUs from the supply graph carry a `G-` or `P-` prefix | Strip it before mapping to an industry-pack key. Buyer products come from graph edges. |
| Sri Lanka customers and hubs are not overseas suppliers | Check the node role, not just the country. |
| `brief.py` is formatted by hand in places (`# fmt: skip`) | Don't run a formatter that rewrites it wholesale. |
| A `Badge` or chip fails contrast | Use the opaque `color-mix` variants; don't add alpha. |
| The remote `m3-c1` history may be rewritten by another session or tool | Never force-push or hard-reset. Use `git fetch origin m3-c1 && git merge --no-edit FETCH_HEAD`. |

## 9. Start prompt for a new session (copy and paste)

```
You are continuing work on Supply Chain Nexus (repo sc_nexus, branch m3-c1).

1. Read, in order: AGENTS.md (rules), handoff.md (map, how-tos, deploy), docs/STATUS.md
   (current state and next steps). Then only the brief/docs rows the task needs
   (AGENTS.md §6; for tariffs: docs/tariffs/BACKEND.md and UI_PLAN.md, ADR-021).
2. Restate the goal in 3–5 lines with the IDs it touches (Cn-Rxx, A-xx, Q-xx, DS-xxx).
3. Locate the code with handoff.md §2 before searching. Respect package boundaries
   (cN imports only core; cross-capability via tables, outbox or service.py).
4. For UI: follow handoff.md §4 and the ui-consistency skills; badges on every data
   surface; tokens only; verify at 1280 px in light and dark with make e2e.
5. For cross-layer work: follow handoff.md §5 in order, with tests at each layer.
6. Ask before schema-shaping choices, scope cuts, licences or sign-ups (≤ 4 questions,
   each with options and a recommendation); continue on unblocked work meanwhile.
7. Done = make check passes, migrations and fixtures included, openapi and gen:api
   regenerated if the API changed, STATUS.md and DECISIONS.md updated, Conventional
   Commits with requirement IDs, pushed to m3-c1 (never force-push).

Task: <describe the task here>
```
