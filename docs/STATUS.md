# STATUS (updated 2026-11-01 BST by Claude Code, Opus 5.5)

Milestone: **M8 Nexus + demo, in progress** (the user deferred VisA and further C5 depth,
U-06). Branch `m3-c1`. Nothing pushed since M2 (commit only until the whole build is done).

Done (M8 slice 1, shipment tracker, NX-R01 / NX-AC02):
- **Door ETA** (`packages/nexus` `door_eta.py` + `tracker.py`, model card
  `docs/model-cards/nexus-door-eta.md`, priors `config/priors/nexus.yaml`, A-092): 1,000-sample
  Monte Carlo over the remaining legs: mode noise, schedules, C4's Chattogram port-call pool,
  container dwell prior, stoppage disruptions at a leg's LOCODE (prob = confidence). Writes
  `prediction` (nexus, `shipment_door_eta`) and `shipment.predicted_eta_p50/p90`.
- **Worker:** `nexus:door_eta` every 15 min, after C2 events and after C4 retrains; job
  `nexus.door_eta`. **API:** `door_eta` on `/shipments[/{id}]` (P10/P50/P90, P(on time), due,
  drivers, holds). **Web:** Control Tower shipments table shows door ETA, on-time and main driver.
- **Results:** 107 open shipments in ≈ 2.5 s; cyclone moves shipments through Chattogram by up to
  +26 h (P50) / +38 h (P90). Mean P(on time) ≈ 0.34: synthetic due dates are only ≈ 5 h after
  the planned delivery (an artefact, in the card).

Done (M8 slice 2, evidence fusion, NX-R03 / NX-AC03):
- `packages/nexus/fusion.py` (model card `docs/model-cards/nexus-fusion.md`, weights
  `config/priors/fusion.yaml`, A-093): logit(conf) = logit(C2 news conf) + Σ weight·strength over
  hazard feeds (GDACS/PortWatch, one per GDACS id), news (for hazard events) and port departures
  (physical, corroboration only); NX-R03 cap; point-in-time (`available_at` ≤ now). One
  `prediction` row per event and scope (real + each scenario); door ETA holds use it.
- Worker `nexus:refresh` (fusion → door ETA; job `nexus.refresh`). API: `confidence_fused`,
  `corroboration`, `fusion_checks` on `/events[/{id}]`. Web: Disruption Radar shows "67% → 86%
  fused" and "corroborated by" chips. Hero news 0.665 → 0.859 (hazard +1.12); e2e asserts it.
- Ops: host rebooted uncleanly; three screenshots have corrupted NTFS entries (user task to repair);
  `docs/screenshots` left out of Docker builds (A-094).

Done (M8 slice 3, recommendation engine, NX-R04 / NX-AC04; card `nexus-recommendations.md`;
`make test` 295 passed):
- `pull_forward_po` alternative to safety stock (feasible share = days until the event ÷ days the
  order needs, upstream exposure via C1 `input_deps`, EV > 0 only, A-095); fused confidence and
  evidence (event + fusion + corroborating events) on Nexus actions.
- Nexus hazard alerts (`alerts.py`, A-096): GDACS/PortWatch forecasts touching a LOCODE now reach
  the engine. Worker `nexus:refresh` = fusion → alerts → recommendations → door ETA (≈ 3 s).
- API `expected_value_usd`, actions ranked by it. Radar drawer: buffer and pull-forward cards with
  expected value, confidence and evidence. Hero cyclone: buffer US$69.1K and pull-forward US$3.8K
  (confidence 0.95); e2e opens it via the Feeds filter.
- Cosmetic gaps (noted): hazard events show "lasts —" (Nexus uses the type prior); the
  corroboration heading says "news confidence" on feed events too.

Done (M8 slice 4, Scenario Studio, NX-R02 / NX-AC05; card `nexus-studio.md`; `make test` 298 passed):
- `studio.py`: baseline vs `nexus_recommended` on the same inputs (C1 cascade at P90 and P50,
  stock added to plant inventory, reroutes saved with Mongla's share, C5 options); K-05 split
  production / quality / in transit, K-06 OTIF, K-07 inland CO2e per TEU + action CO2e; stored as
  `scenario_result` (nexus) by the worker's `nexus:refresh`. Page: Scenario Studio (tiles,
  comparison, actions, one-page PDF export). Hero: net +US$98.4K, OTIF +1.6 pts, P90 production
  late 5.0 → 3.8, revenue at risk US$1.87M → US$1.20M.
- Bug fixed on the way (A-098): stock was proposed for orders blocked at the shut gateway; the
  engine now proposes `reroute` via Mongla for those and stock only for input shortages; engine
  and studio share one disruption window. Golden-path step 5 now shows "export via Mongla".

Done (M8 slice 5, backtest, NX-AC06; card `nexus-backtest.md`, `uv run nexus backtest`):
- Real data 2023-01-01 → 2026-10-22 (27,292 GFW departures at Chattogram, GDACS/PortWatch):
  7 alerts, 28 port-data episodes; K-04 precision 0.43 (3 of 7), recall 0.07 (2 of 28), K-03
  lead median 43.5 h (34 h May 2023 flood, 53 h Hamoon). False alarms: two cyclones that turned
  away, two earthquakes. Misses: 10 of 26 labelled (8 Eid, the 2024 unrest, Remal at 357 km).
  Hazard feeds only: no news history before Oct 2026.

Done (M8 slice 6, golden path, NX-AC01; script `docs/GOLDEN_PATH.md`):
- `make golden`: offline worker (`CPORTAL_LIVE=0`, `CPORTAL_LLM=0`), demo reset, timed compute
  (`cportal-golden`): C1 → C5 → Nexus for the hero in ≈ 4.5 s (budget 30 s).
- `make golden-walk`: Playwright walks the 8 steps with every non-local request aborted; 5.2 s of
  machine time; only `tiles.openfreemap.org` was blocked (basemap), the story still works →
  `docs/golden-path.json`. Presenter script with the live numbers per step.
- Fix: the studio's K-07 no longer crashes without DESNZ factors (unknown, shown as "—").

Done (Control Tower redesign, user request 2026-11-03; U-07, A-101, A-102):
- Data selector: real data by default (Today estimated / Yesterday / Tomorrow forecast / custom
  date) or synthetic scenarios with plain names; API `day` param resolves Dhaka days (scope
  `as_of`, meta `horizon`); "Estimated" / "Forecast" chips on the KPIs.
- Real KPIs from GFW port calls at the view time (46 vessels in the port area, median 53.6 h in
  port, observed 23 Oct); no synthetic badge or invented order book in real mode.
- Disruption events open their news source (synthetic `.example` articles are not linked).
- "Ships at Chattogram" replaces the shipments table: real ship names, status filters, hover card,
  estimated dock time (scenario baseline; "not observable" in GFW), cargo where known.

Done (keys added by the user, 2026-11-03; A-103…A-105):
- TomTom probed: no live traffic in Bangladesh (blocked); Mapbox lists Bangladesh (user decides).
- DataDocked: hover-card "Look up owner & P&I" (3 trial credits, cached a year, 5/day cap);
  DING HENG 50 cached (owner, manager, class; P&I not on record).
- aisstream global probe (`uv run ais-bd-bound`): BD-bound ships exist in the feed but trickle
  (Indian Ocean coverage thin) → needs an always-on collector.
- Drive: the three `?????` screenshot entries are still there (remount does not repair NTFS).
- Route Planner traffic (A-106): Mapbox live congestion tiles (proxied, Bangladesh only) or
  C3's modelled zones (Dhaka hour profile, truck ban), with a Live / Modelled / Off control.
  TomTom has none (A-103). Plan ETAs still from C3's model (Mapbox ETA factor: next).
- Screenshots paused on Quality Lab e2e (corrupted files; docs later, per the user).

Next: BD-bound collector in the worker (sightings into `ais_position_latest` with destination
and AIS ETA; "Expected" ships with region) → refresh GFW + C4 so Today/Tomorrow are real
nowcasts/forecasts → traffic alternative (user) → continue Scenario Studio → deepen C1–C5.

Checks: `make test` 294 passed (after slice 2); slice 1: 289 passed (latency budgets included; before a host reboot they ran at
≈ 330 ms for every route, unchanged ones too); Control Tower e2e passes, screenshots refreshed.
Cosmetic gaps (noted, not fixed): the on-time badge wraps "47 %" onto two lines; most rows name
"schedules and connections" as the main driver.

Waiting on user: **Q-17** (copilot "Ask Nexus" / MCP server: skip, read-only copilot, or both).

---

Done (M7, C5 defect intelligence):
- **Data:** `uv run vis-fetch`: MVTec AD pill, capsule, carpet, leather (test sets, masks, 60
  normal training images each; NC) and StitchNet v2 (483 garment-stitching images, CC BY 4.0)
  into `data/raw/`, never committed (A-084).
- **`packages/c5_defect_intel`** (ADR-020, model card `docs/model-cards/c5-defect-intel.md`):
  DINOv2-S as ONNX on the CPU; AnomalyDINO-style few-shot and MuSc-style zero-shot scoring with
  heatmaps and tiling; thresholds at 5 % FPR on held-out normals; `c5 eval` writes the report,
  the gallery (`data/c5/`) and the live few-shot banks (`models/c5/`).
- **Lots:** ISO 2859-1 (Table 1 and Table 2-A, checked cell by cell against ANSI/ASQ Z1.4);
  model-assisted counts (confirmed = flagged and real); pharma always held for QA.
- **Risk and SPC:** beta-binomial lot risk per line (Brier vs base rate, reliability); p-chart
  and EWMA alarms. **Impact:** failed lot → order at risk → alert with rework, replacement, air
  and buyer-notice options, each with cost and benefit (C5-AC06). Plant lot quality now feeds C1.
- **Simulator (world 0.3.0):** finished-goods lots on factory lines, linked to their orders
  (`batch.order_id`, migration), a drifting line and a QA hero lot whose order is at risk.
- **Results:** image AUROC few-shot k = 8 / zero-shot: stitch 0.89 / 0.71, pill 0.97 / 0.95,
  capsule 0.96 / 0.93, carpet 1.00 / 1.00, leather 1.00 / 1.00 (pixel AUROC 0.96–0.99 on
  MVTec; textures scored untiled, A-091); ≈ 0.4 s per image on CPU (C5-AC02);
  few-shot rises with k (AC03); AQL tables and OC checks pass (AC04); lot risk Brier 0.046 vs
  0.057 base rate (AC05); 15 failed lots → 15 alerts, 32 costed options (AC06); 8.1 % of
  garment lots escape because the model misses defects (reported as the assistive cost).
- **Worker:** `c5:refresh` (inspect waiting lots, risk, impact). **API:** `/quality/summary`,
  `/quality/batches[/{id}]`, `/quality/lines[/{id}/spc]`, `/quality/gallery`, `POST
  /quality/inspections` (live, ≈ 0.5 s), `/quality/files/…`. **Web:** Quality Lab.
- **openrouteservice** (A-083): 429/403 handling and persisted answers.

- **Since the thin slice (2026-11-01):** MVTec carpet and leather evaluated (gallery, banks,
  model card); AnomalyCLIP baseline script, setup and manifest in
  `packages/c5_defect_intel/baselines/` (U-05: the user runs it); stack rebuilt (`make up`),
  quality routes 57–198 ms warm; `make test` 280 passed.

- **AnomalyCLIP baseline (C5-AC01, met):** user's run (U-05): stitch 0.67, pill 0.82, capsule
  0.90, textures ≈ 1.00; our methods beat it on every object category and tie on textures;
  ≈ 1.8× slower on CPU. Script now shows tqdm progress bars.

Not met yet (honest): VisA capsules
(optional download, U-04); thresholds over-shoot the 5 % FPR with 30 calibration images (stitch
14 %, capsule 9 %, carpet 25 %: MVTec test normals score above train normals); no evaluation
notebook yet (CLI + JSON).

Waiting on user:
- **VisA capsules: deferred** by the user (deepen C5 later). Data and split file are in
  `data/raw/DS-VIS-02/`; scoring ran, but saving the `model_version` row failed (psycopg
  parameter error, not yet diagnosed).
- Soft gate: deepen C5 (AnomalyCLIP, VisA, a notebook, few-shot upload flow) or move to M8?

---

Earlier (M6, C4 port dwell, Chattogram):
- **Data:** `uv run gfw-backfill`: 28,160 real GFW port visits (2023 →) and 164,651 anchorage
  presence rows (A-076); DMA AIS, all seven days in the inbox (03-01 re-fetched).
- **`packages/c4_port_dwell`** (ADR-019, model card `docs/model-cards/c4-port-dwell.md`):
  labels and cleaning; point-in-time features with an observer lag (leakage test, C4-AC07);
  L0 median; L1 LightGBM P10/P50/P90 + MAPIE CQR with TreeSHAP drivers; L2 random survival
  forest for remaining time; L3 direct LightGBM queue forecast with conformal bands.
- **Results (test 2026-07-10 → 09-08):** cargo dwell MAE −17.8 % vs median (C4-AC03), 80 %
  intervals cover 81–83 % (AC04), survival C-index 0.65 and IBS 0.162 vs 0.193 KM (AC05), queue
  MASE 1.16 vs 1.26 and WQL 0.071 vs 0.085 at 7 days (AC06).
- **Worker:** `c4:train` daily and after DS-AIS-02 ingests; replay predictions in `prediction`.
- **API:** `/ports/{locode}/forecast`, `/ports/{locode}/predictions`, `/vessels/{id}/prediction`
  (11–28 ms).
- **Web:** Ports & Vessels: snapshot slider, KPIs, anchorage fan chart with what happened,
  vessel table with departure windows and actual outcomes, drawer with drivers and the
  estimate's track. E2E test added.

Not met yet (honest): C4-AC02 (AIS state machine on DMA vs GFW), all-vessel AC03 (12.3 %),
queue band under-covers (69 %), satellite panel (Q-15 default: SAR counts + thumbnails), weather,
tide, holiday and C2-event features, vessel size, a TSFM, Mongla.

Resolved since: the user chose C5 next.

---

Earlier (M5, C3 routing):
- **`packages/c3_routing`** (ADR-018, model card `docs/model-cards/c3-routing-baseline.md`): own
  road graph from the Geofabrik extract (16,110 edges, motorway → secondary, 11 s); time-dependent
  truck speeds with a Dhaka rush-hour profile and the user-verified truck ban (08:00–20:00);
  road, road + rail (Kamalapur) and road + barge (Pangaon) chains; Monte Carlo P50/P90 and
  on-time probability; cost from cited tariffs; CO2e per leg from DESNZ rows; Pareto rank;
  departure sweep. Chattogram → Gazipur: 4 non-dominated plans in 1.3 s (C3-AC02).
- **Calibration vs ORS HGV** (C3-AC01): distances within 3.2 %, route times within 1.8 % after
  one factor; the factor (1.64) is reported, not applied (A-075, user task to find a real
  truck time).
- **Fix:** hour lookups (ban, profiles, timetables) now use Dhaka time; they ran on UTC (A-074).
- **API:** `/routes/places`, `/network/services`, `POST /routes/optimize`, `/routes/{id}`.
- **Web:** Route Planner: form, Pareto chart, route map, plan cards with mode mix and on-time
  odds, "when to leave" strip, cited factors. E2E test added.
- C2: `qwen3:4b` is the default `LLM_MODEL` (gold-set F1 0.43 vs rules 0.30; A-073).

Not met yet (honest): C3-AC05 (C2 closures and C4 dwell don't change plans yet), cargo
exemptions to the ban, a measured truck speed level; C2-AC01 F1 (rules 0.30).

Resolved since: the user chose C4 next; C3 deepening later.

---

Earlier (M4, C2 trade-news intelligence):
- **`packages/c2_trade_news`** (ADR-017, model card `docs/model-cards/c2-rules-baseline.md`):
  gazetteer + regex extraction with a character span for every field; relevance, type, places,
  start, duration, size, status; clustering into events (a hazard and the closures it causes are
  one event); severity and confidence (independent outlets, single-source cap 0.5); alerts.
  Real articles → real events; each scenario's synthetic articles → that scenario's events.
- **Local LLM** (`cportal_core.llm`, Ollama, JSON-schema constrained, grounded): a second
  opinion on the top-K, stored as predictions. `llama3.1:8b` rejected 12/12 with 9 ungrounded
  quotes; `qwen3:4b` is being pulled for a comparison.
- **`packages/nexus`** (A-064): buffer recommendations per open alert and scenario from C1's
  what-if and the safety-stock formula; accept / dismiss.
- **Worker:** `c2:process` every 15 min and after each news ingest (→ C1 refresh → buffers);
  `c2:llm` hourly when Ollama is reachable.
- **API:** `/events` (source, confidence, since filters), `/events/{id}` with mentions and
  evidence spans, `/alerts` + ack, `/recommendations?kind=buffer` + decision, `/events/extract`.
- **Web:** Disruption Radar: feed, event map, drawer with highlighted evidence, linked plants,
  buffer card with Accept / Dismiss. Hero scenario: one CYCLONE_STORM event at Chattogram from
  five reports (severity 0.80, confidence 0.67) and a buffer recommendation (≈ 2.4 days of cover
  on two inputs, benefit ≈ US$48k vs ≈ US$26 holding cost).
- **Data:** DMA AIS (DS-AIS-03) one day in the inbox + sample; Data Docked (DS-AIS-06) probed,
  internal use only (A-057, A-058). Ocean backdrop with glass cards (A-059).
- Tests: C2 unit tests (11), API tests for events / alerts / decisions, e2e for the Radar
  (6 Playwright tests green). Screenshots `docs/screenshots/disruption-radar-*`.

Not met yet (honest): C2-AC01/AC02 F1 (needs the gold labels), C2-AC07 backtest, GLiNER2
(deferred, A-060), grounded-LLM ≥ 95 % (llama3.1 fails it).

Resolved since: gold labels (F1 measured), `qwen3:4b` benchmarked, Ollama restarted, Q-12.

---

Earlier (M3, C1 supplier risk graph):
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
