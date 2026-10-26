# STATUS (updated 2026-10-27 BST by Claude Code, Opus 5.5)

Milestone: **M2 Backbone complete → gate G2 (hard stop: waiting for the user's review).**
Next after approval: M3 (C1 supplier risk graph), starting with Q-12 (GNN scope).

Done (M2, branch `m2-backbone`):
- **Worker** (`apps/worker`, `make worker` or the compose `worker` service): APScheduler jobs
  for the 7 verified live sources (GDELT GKG, RSS, ReliefWeb, openFDA, World Bank, Open-Meteo,
  GDACS) on their card cadences; two strikes then a 6 h cool-down and a `source.degraded`
  outbox event (ADR-011); raw archives with secrets redacted; outbox drained on
  LISTEN/NOTIFY with `FOR UPDATE SKIP LOCKED`; `scenario.run` job; JSON logs; stops cleanly
  on SIGTERM.
- **AIS replay:** the hero scenario's port DES re-rendered as aisstream frames through the real
  parser every 5 s (30×, 48 h loop), pushed to `ais_position_latest` with `pg_notify`.
- **API:** `/api/v1/kpis` (5 KPIs, each with its own badge), `/ws/live` (position snapshots
  when the scenario's replay clock moves), `/shipments?active=true`, richer `/sources`
  (licence, cadence, effective mode, failures, last error).
- **Web** (`apps/web`, ADR-015): Next.js 16 (Cache Components), Tailwind v4 Tidewater tokens,
  light/dark with a persisted toggle, scenario switcher (hero, baseline, real only), brand
  from `CPORTAL_BRAND_NAME`. Control Tower: KPI strip, live MapLibre anchorage map with legend
  and replay clock, disruption feed, open shipments. Data & Models: 48 sources with status,
  mode, freshness, rows and licence (NC flagged), scenario projections, models placeholder,
  attributions. Six other pages are labelled placeholders for M3–M8.
- **Compose:** `make demo` builds and starts db, migrate, api, worker and web, seeds, and
  restarts the worker; verified from empty volumes in a throwaway project (≈ 2 min; seed 32 s).
- **Tests:** 213 Python tests (incl. the replay-clock and active-shipment regressions), ruff,
  import-linter, mypy, `tsc`, ESLint; Playwright smoke (4 tests) green against compose.
  Screenshots (1280 px, light and dark) in [docs/screenshots/](screenshots/).
- Docs: ADR-015, decisions Q-07 answer and A-044…A-050, README quickstart.

Fixed during M2 checks: MapLibre 6's worker URL under the bundler, the map container collapsing
to 0 px under MapLibre's CSS, the first snapshot arriving before the map loaded, real AIS rows
freezing the replay clock, past-ETA shipments shown as in transit, the worker ignoring SIGTERM
for up to 30 s.

In progress:
- Nothing half-written.

Next (after G2):
1. M3 / C1: thin slice of the supplier risk graph (graph from the synthetic world, criticality
   metrics, what-if closure job, Supplier Network page). Ask Q-12 (GNN scope) first.
2. M4 / C2: trade-news intelligence with the local LLM (Ollama 0.40 is installed; no model
   pulled yet; ≈ 7 GB RAM suggests a 3–4 B model, to be proposed then).

Blockers: none.

Waiting on user:
- **G2 review** of the running stack (`make demo`, then http://127.0.0.1:3000).
- Q-12 at M3 start; the Ollama model choice at M4.
- Optional: more CPA berthing PDFs into `data/inbox/DS-PORT-07/`; Copernicus login.

Known limits (honest list):
- The basemap needs internet (OpenFreeMap); the offline Protomaps extract is planned for M8.
- AIS is synthetic replay: aisstream has no Bangladesh coverage (A-019, U-01).
- KPIs "mean wait" and "orders at risk" are observed or rule-based, not forecasts; forecasts
  arrive with C4 (M6) and Nexus (M8). The hero scenario's port effect is modest in DES v0.
- The e2e test checks the map's vessel count and idle state, not pixels; screenshots were
  reviewed by eye.

Data modes: DS-AIS-01=synthetic (replay of the scenario DES), DS-AIS-02=replay,
DS-SAT-04=replay, DS-PORT-01=replay, DS-PORT-05=replay, DS-PORT-07=replay (manual PDF),
DS-WX-01=live, DS-WX-02=live, DS-NEWS-02=live, DS-NEWS-03=live, DS-NEWS-04=live,
DS-PHARMA-01=live, DS-TRADE-03=live; the rest replay from committed samples or are off
(see the Data & Models page).

Model versions active: none (baselines register from M3).

Demo health: `make demo` → Control Tower shows the hero scenario (Cyclone SYN-01 + Mill X
delay) with moving vessels; golden path script comes in M8.
