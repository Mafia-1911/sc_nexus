# STATUS (updated 2026-10-27 BST by Claude Code, Opus 5.5)

Milestone: **M3 / C1 thin slice done → soft gate: deepen C1 or move to C2?** (G2 approved;
`main` = M2.) Branch `m3-c1`.

Done (M3, C1 supplier risk graph):
- **World v0.2** (A-051): 151 nodes (146 fictional facilities + Chattogram and two hubs), 955
  supply relationships, 140 open orders; four planted sole sources; capacities and stock from
  open-order demand. Seeding replaces a scenario's rows (A-052); seed ≈ 35–48 s.
- **`packages/c1_supplier_graph`** (ADR-016, model card `docs/model-cards/c1-baseline.md`):
  AND/OR removal test for single points of failure, dependency reach, HHI, centralities;
  TTS/TTR and performance impact as HiGHS LPs; daily cascade what-if with backorders,
  re-sourcing, gateway closures and hub reroutes; Monte Carlo P50/P90; transparent risk score
  with exact Shapley drivers; mitigation hints. Imports only core (lint contract).
- **Data:** `graph_metric`, `whatif_result` (one migration). Worker `c1:refresh` every 5 min by
  input fingerprint and immediately on `disruption.*` events; `c1.whatif` Monte Carlo job.
- **API:** `/graph` (network + map), `/graph/critical`, `/graph/nodes/{id}`, `POST
  /graph/whatif` (sync, or 202 with Monte Carlo), `/graph/whatif/{id}`. Risk views always use
  fictional names (Q-05).
- **Web:** Supplier Network page: layered network (Sigma.js) ↔ map, industry filter,
  leaderboard (single points of failure / TTS vs TTR / risk), node drawer (drivers, TTS vs TTR,
  inputs and HHI, linked events, orders with no other path), what-if panel with timeline,
  late orders and mitigations; ripple highlight on the graph.
- **Acceptance (C1-AC01–AC05):** 151 nodes; planted sources recalled 20/20 over five seeds
  (ranks 1–6), gateway first every time; TTS < TTR for every planted source; what-if < 2 s;
  200 Monte Carlo runs ≈ 11 s and reproducible; drivers exact. AC06: linked events raise the
  score ("Open disruption events linked +11" on Mill X) and pre-fill the what-if.
- Tests: 233 Python + 5 Playwright, all green; screenshots `docs/screenshots/supplier-network-*`.

Findings:
- In the hero scenario, Mill X's linked event is a 5-day delay, and plants hold ≥ 7.9 days of
  denim, so the default what-if shows no late orders; a 21-day outage makes 5 orders late
  (US$3.7M, P90 US$8.8M). The brief's "TTS 4 d < TTR 9 d" was illustrative; these are the
  model's numbers.
- DS-RISK-01's committed sample is an API error, so the registry said "verified" wrongly; now
  `blocked` (A-054).

In progress: nothing half-written.

Next (your choice at this gate):
- **Deepen C1:** Monte Carlo in the UI; LightGBM vs the baseline on simulator labels; GNN per
  Q-12; hazard from IBTrACS; SupplyGraph validation.
- **Or move to C2** (Disruption Radar, M4) with the local LLM: `llama3.1:latest` (8B Q4, 4.9 GB)
  is pulled; with ≈ 7 GB RAM and the Docker stack running it will be tight, so the plan is
  GLiNER-style extraction and rules first, the LLM only for the top-K articles.

Blockers: none.

Waiting on user: deepen C1 or move to C2; **Q-12** (GNN scope).

Known limits: cosmetic UI gaps are left as is (overlapping labels when zoomed out, small
nodes); the risk score is uncalibrated (no labels); the basemap needs internet.

---

Previous milestone (M2, kept for reference):

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
