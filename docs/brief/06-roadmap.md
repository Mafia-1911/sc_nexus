# 06 · Roadmap, acceptance criteria and cut lines

**TL;DR.** The plan assumes about four weeks (≈ 26 working days). Confirm the real deadline at kickoff (Q-01) and rescale. Design and backbone come first (M0–M2, with hard gates G0–G2), then one **thin end-to-end slice** per capability in build order. Deepen a capability only once its slice demos. Every milestone ends in something visible in the browser. If time runs short, apply the **cut lines** in §3, never quality shortcuts such as dropping tests or faking data.

## 1. Milestones

| M | Days (≈) | Goal | Key tasks | Exit / acceptance |
|---|---|---|---|---|
| **M0 Recon** | 1–2 | Know the data | Minimal scaffold; probe harness; probe every P0 source (then P1); start the AIS collector; source cards; `PROBE_REPORT.md`; kickoff questions | **G0:** every P0 source has a card with status, auth, limits, licence and Bangladesh coverage; raw samples committed; a "needs you" list; proposed schema changes with evidence |
| **M1 Architecture** | 2–3 | Freeze contracts | ADR-001…010; final domain model v1; Alembic migrations; Pydantic schemas; OpenAPI skeleton (all routers, stub responses); `sim` world v0 + port DES v0; `CALIBRATION.md`; contract tests real ↔ synthetic | **G1:** `make test` green; contract tests pass for every P0 source; the synthetic world seeds in < 60 s; ERD and ADRs reviewed |
| **M2 Backbone** | 4–6 | A platform you can click | docker-compose (db, api, worker, web); connectors in live, replay and synthetic modes; scheduler + outbox; web shell with Tidewater tokens; **Control Tower** (map with live or replayed AIS, KPI strip from synthetic data, alert feed stub); **Data & Models** page; Playwright smoke test | **G2:** `make up && make seed && make demo` works from a clean clone; the live map shows Chattogram vessels (live or replay); the data-mode badges are correct; e2e smoke test green |
| **M3 C1** | 7–9 | Supplier risk graph | Graph build; dominators, downstream counts, HHI and centralities; TTS/TTR LP; cascade what-if; UI graph and map; (stretch) GNN in a notebook | C1-AC01…AC06 |
| **M4 C2** | 9–12 | Disruption radar | GDELT, RSS, GDACS and openFDA ingest; triage; GLiNER2 extraction; LLM top-K (per Q-03); geocode and link; clustering; severity and confidence; alerts; buffer recommendations; backtests | C2-AC01…AC08 |
| **M5 C3** | 12–15 | Route planner | Corridor graph (road + rail + barge services); cost, time, CO2e and reliability models; Pareto planner; departure windows; UI; (stretch) PyVRP multi-drop, RL experiment | C3-AC01…AC07 |
| **M6 C4** | 15–19 | Port dwell | Geofences; port-call state machine; GFW labels; feature store; median → LightGBM quantile + conformal; survival model for remaining wait; TSFM queue forecast; satellite panel; (stretch) multimodal transformer from a notebook | C4-AC01…AC08 |
| **M7 C5** | 19–22 | Quality lab | ZSAD benchmark notebook (≥ 2 methods); CPU export; inspection API; tiling; AQL lot logic; defect-rate forecast + SPC; impact on orders; UI | C5-AC01…AC07 |
| **M8 Nexus + demo** | 22–26 | One story | Scenario engine; evidence fusion; recommendations; shipment tracker; daily brief; golden-path script and reset; performance pass; README with screenshots; 3-minute video | **G3:** golden path in replay mode without network in < 7 min; NX-AC01…AC06; polish checklist (`05-ui-design.md` §10) complete |

**Soft gate per capability (M3–M7).** When a capability's thin slice works end to end (data → model/baseline → API → UI), post a five-line summary with a screenshot and metrics. Then ask: *"Deepen Cn (list of options) or move to Cn+1?"*

## 2. Thin-slice definition (for each capability)

1. Real-mode data where available, otherwise replay, otherwise synthetic (per `config/sources.yaml`).
2. A **baseline** model or rule, with metrics on a time-based holdout.
3. A `service.py` predict function within its CPU budget.
4. The API endpoint returning `meta` (mode, sources, model version).
5. The UI page with data badges, an explanation and uncertainty.
6. Tests (unit, contract, golden), a model card and a STATUS update.

## 3. Cut lines (apply in order when behind schedule)

| If short by | Cut |
|---|---|
| ~3 days | C3 RL experiment; C1 link prediction; C5 VLM explanations; Bangla translation |
| ~6 days | C1 GNN (keep the analytics and simulation); C4 custom transformer (keep LightGBM, survival and TSFM); C3 VRP |
| ~9 days | C2 LLM extraction (keep GLiNER2 and rules); C4 satellite beyond the GFW SAR counts; Scenario Studio limited to the golden-path scenario |
| ~12 days | Pharma variant of the demo (keep garments as the hero); C5 forecasting (keep inspection + AQL + impact) |

**Never cut:** probe-first data work, data badges, baselines with honest metrics, tests at the boundaries, or the golden path itself.

## 4. Demo script (G3)

1. **0:00–0:30** Problem in one sentence, plus one Chattogram fact with its source (from `01-product.md` §1, re-verified).
2. **0:30–5:30** Golden path (`01-product.md` §5), driven by `make demo`. Each step shows evidence, uncertainty and trade-offs.
3. **5:30–6:30** "How it works": the architecture diagram, plus the list of open data sources (with the LIVE, REPLAY and SYNTHETIC split) and models used.
4. **6:30–7:00** Impact (KPIs from the scenario comparison) and next steps (real-data swaps, pilots).

Back-ups: a recorded video of the golden path, screenshots in the README, and the replay dataset bundled locally.

## 5. Risk register (watch weekly)

| Risk | Signal | Mitigation |
|---|---|---|
| Thin AIS coverage at Chattogram (aisstream) | Low message counts in M0 | GFW presence and port visits as history; DES calibrated to them; replay recordings for the demo |
| API limits or blocks mid-demo | 429s, outages | Replay mode is the demo default; caches; precomputed predictions |
| ZSAD domain gap on fabric | Low AUROC on fabric sets | Few-shot (AnomalyDINO) with a handful of normal images; tiling; honest card |
| Scope creep | Milestones slipping | Cut lines; soft gates; golden path first |
| Licence issues (NC data) | — | Flags on the Data & Models page; non-commercial hackathon use only (Q-06) |
| Wrong facts in the brief | Probe contradicts the brief | Agent updates the registry and logs it in DECISIONS.md (AGENTS.md §7) |
