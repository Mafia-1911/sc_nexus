# Gap analysis, theme fit and feature proposals (2026-11-18)

**TL;DR.** The platform is far along: backbone, C1–C5 thin slices (several deepened) and five of
six Nexus slices are built, tested (`make test` 330 passed on 2026-11-17) and partly deployed.
The biggest gaps are **against the hackathon theme wording**, not against the brief: the themes
name a *transformer* with *satellite imagery* (C4 has neither in the UI), a *GNN* (C1 has none)
and an *RL agent* (C3 has none). Inside the brief, the main logic gaps are that C2/C4 do not
change C3 route plans (C3-AC05), C3's speed level is 1.64× off ORS and not applied, the FX rate
is a hard-coded estimate, and the teammate's PR (Mafia-1911/sc_nexus#1) cannot merge as is. The
proposed new feature with the best demo value per day of work is the **Tariff & Trade-Policy
Monitor** (plan: [`C6-tariff-monitor-plan.md`](C6-tariff-monitor-plan.md)); four free sources
for it were probed today and work.

Method: read `AGENTS.md`, `docs/STATUS.md`, `docs/DECISIONS.md`, the brief (`00`, `06`, `07`,
C1/C3/C4 cards), model cards, code greps, and the teammate PR's diff. Every "gap" below cites the
file or check it comes from. Items marked *(verify)* are facts from outside the repo that need a
source check before they go in the demo.

---

## 1. What the project is and which files do what

| Area | Where | What it does |
|---|---|---|
| Standing brief | `AGENTS.md`, `docs/brief/*` | Mission, decisions D-01…D-10, hard rules, milestones M0–M8, gates |
| Running record | `docs/STATUS.md`, `docs/DECISIONS.md`, `docs/SESSION_LOG.md`, `docs/USER_TASKS.md` | What is done, assumptions A-001…A-124, user answers U-xx, user tasks |
| Architecture | `docs/adr/ADR-001…020`, `docs/ERD.md`, `docs/api/` | One ADR per choice; ERD; OpenAPI |
| Data registry | `config/sources.yaml`, `docs/data-sources/DS-*.md`, `data/samples/DS-*` | ~48 sources, cards, raw probe samples (D-08) |
| Shared core | `packages/core` | ORM models with lineage (`is_synthetic`), schemas, enums, LLM client, scope rules |
| Connectors | `packages/connectors` | One module per source (`ds_<domain>_<nn>_*.py`), polite HTTP, raw archive |
| Synthetic world | `packages/sim`, `config/world`, `config/industry_packs`, `config/scenarios` | Fictional firms at real clusters, BOMs with real HS6 codes, hero cyclone scenario, port DES |
| C1 supplier graph | `packages/c1_supplier_graph` | SPOF removal test, HHI, centralities, TTS/TTR LPs, cascade what-if, Monte Carlo, Shapley drivers |
| C2 trade news | `packages/c2_trade_news` | Gazetteer + regex extraction with spans, event clustering, severity/confidence, local LLM second opinion |
| C3 routing | `packages/c3_routing` | Own OSM road graph, rail/barge chains, Monte Carlo P50/P90, cost, CO2e (DESNZ), Pareto set, departure sweep |
| C4 port dwell | `packages/c4_port_dwell` | GFW labels, point-in-time features, LightGBM quantiles + CQR, survival forest, queue forecast, berth-wait model |
| C5 defect intel | `packages/c5_defect_intel` | DINOv2 ONNX few/zero-shot anomaly scoring, ISO 2859-1 AQL, beta-binomial lot risk, SPC, order impact |
| Nexus | `packages/nexus` | Door ETA, evidence fusion, hazard alerts, recommendations (buffer, pull-forward, reroute), Scenario Studio, backtest, daily brief |
| Apps | `apps/api` (FastAPI), `apps/worker` (APScheduler + outbox), `apps/web` (Next.js 16) | 8 pages: Control Tower, Ports & Vessels, Supplier Network, Disruption Radar, Route Planner, Quality Lab, Scenario Studio, Data & Models |
| Deploy | `deploy/`, `render.yaml`, `scripts/deploy_*.sh` | Vercel web (live), Neon DB (live), Render API (not answering yet) |

**The plan being followed** (`docs/brief/06-roadmap.md`, `AGENTS.md` §5): M0 recon → M1
architecture → M2 backbone (gates G0–G2 passed) → M3–M7 C1…C5 as thin slices → M8 Nexus and demo
(in progress) → G3 final review. Since 2026-11-17 the user's order is "show first, make better
later": deploy, then deepen the layers (U-09).

## 2. State of each feature (from `docs/STATUS.md` and the model cards)

| Capability | State | Honest open items (source) |
|---|---|---|
| Backbone (M2) | Done | — |
| C1 | Thin slice + C2/C5 inputs | Risk score uncalibrated (no labels); no GNN (Q-12: stretch); LightGBM vs baseline not run; Monte Carlo not in UI |
| C2 | Rules + LLM (`qwen3:4b`) | Gold-set F1 0.43 (LLM) / 0.30 (rules), below C2-AC01; no backtest (C2-AC07); no news history before Oct 2026 |
| C3 | Pareto planner, live Mapbox factor | **C3-AC05 not met:** C2 closures and C4 dwell do not change plans; speed level 1.64× slower than ORS, factor reported not applied; no RL (Q-14 default) |
| C4 | Deepened (berth-wait model beats baseline) | **No satellite panel** (Q-15 default: GFW SAR counts + Sentinel thumbnails; connectors `ds_sat_01_cdse.py`, `ds_sat_04_gfw_sar.py` exist, no UI); no transformer/TSFM; queue band under-covers (69 % for an 80 % band); no weather/tide/holiday features; Mongla absent |
| C5 | Deepened | Thresholds over-shoot 5 % FPR on held-out normals (14–25 %); VisA deferred; no evaluation notebook |
| Nexus | 6 slices done | Backtest recall 0.07 (hazard feeds only); copilot declined (Q-17 → no) |
| Deploy | Partial | Render API not answering (user task) |

## 3. Gaps where logic or implementation is not correct (verified in code)

Ordered by how much they could hurt the demo or a judge's question.

| # | Gap | Evidence | Why it matters | Suggested fix (size) |
|---|---|---|---|---|
| G-1 | **Routes ignore disruptions.** C3 plans don't read C2 events or C4 dwell. | `grep` of `packages/c3_routing/src/cportal_c3/*.py`: only transfer-dwell priors; STATUS "C3-AC05 not met" | The cyclone story says "reroute via Mongla", but the Route Planner shows the same plans with or without the cyclone. A judge clicking through will see it. | Read open events touching a LOCODE/area through `c2` service or the `event` table; close or slow matching edges/services for the event window; use C4's P50/P90 wait at the port node. (S–M, 1–2 days) |
| G-2 | **Truck speed level is off by 1.64×** and not applied. | `docs/model-cards/c3-routing-baseline.md` lines 28–41 | Route ETAs could be wrong by a factor; door ETA inherits them. | Keep the user task (one dated truck time) but show the range in the UI ("ORS would say 3.7 h"), or apply a midpoint with a note. (XS) |
| G-3 | **FX is a constant** (BDT/USD 122, `fx_rate` table empty). | `config/priors/c3.yaml:22`, A-069 | Every BDT→USD cost and the recommendation EVs depend on it. Easy to question. | World Bank WDI `PA.NUS.FCRF` (already connected, DS-TRADE-03) or Bangladesh Bank's published rate; fill `fx_rate`, fall back to the prior. (XS) |
| G-4 | **Synthetic due dates make P(on time) ≈ 0.34.** | STATUS M8 slice 1 | An average on-time chance of 34 % looks broken in the shipments table. | Re-seed due dates from lead-time priors plus slack (sim change), recompute. (XS) |
| G-5 | **C5 thresholds miss their FPR target.** | C5 model card, A-124 | "5 % false alarms" claims would be wrong; card is honest, the UI should be too. | Show the held-out FPR next to each threshold in Quality Lab. (XS) |
| G-6 | **C4 queue band under-covers** (69 % for 80 %). | STATUS M6 | The fan chart overstates confidence. | Widen with the conformal quantile on a recent window, or label the band "nominal 80 %, 69 % observed". (XS) |
| G-7 | **Teammate PR conflicts with the current tree.** | `git diff` of Mafia-1911/sc_nexus#1 against its base `8d9d781` (2026-10-27, pre-M3) | See §4. | Port the idea, do not merge. |
| G-8 | **Cosmetic gaps already noted** (hazard events "lasts —", "news confidence" label on feed events, 47 % wrapping) | STATUS | Small polish items judges notice. | (XS each) |

## 4. The teammate PR (Mafia-1911/sc_nexus#1, "Universal Quality AI")

What it adds: a second C5 package `packages/c5_quality` (Anomalib **WinCLIP** zero-shot, PyTorch),
a Gradio demo, `routers/quality.py`, a `/quality` page with an upload inspector, samples and a
smoke test (32 files, +3,269 lines).

Why it cannot merge as is (checked in the diff):

1. **Stale base.** It branches from `8d9d781` (end of M2). The tree has since gained C1–C5,
   Nexus and the `(app)` route group.
2. **Import-name collision.** Both `packages/c5_quality` and the existing
   `packages/c5_defect_intel` install the module `cportal_c5`.
3. **Route collision.** It adds `apps/web/app/quality/page.tsx`; the app already has
   `apps/web/app/(app)/quality/page.tsx`. Next.js rejects two pages for one path.
4. **Router collision.** It adds `apps/api/.../routers/quality.py`, which exists already.
5. **Weight.** PyTorch + Anomalib in the API image (+1,356 lines in `uv.lock`) against D-03's
   CPU-only, lean inference (the current C5 runs DINOv2 as ONNX).
6. **Global TLS monkeypatch** in `engine.py` (`ssl._create_default_https_context = ...`)
   changes TLS for the whole process.
7. Removes 114 lines from `apps/web/package-lock.json`; adds a 4.3 MB screenshot and duplicate
   sample images.

What is worth keeping: **text-prompted zero-shot inspection of any product** ("a photo of a
damaged capsule") with an upload box is a good demo idea. The current C5 already has `POST
/quality/inspections` (≈ 0.5 s). Proposal: add WinCLIP-style text prompts as an option in the
existing C5 (CLIP ONNX, compared against DINOv2 on the same split per rule 5), and reuse the
PR's upload-and-heatmap UI pattern inside the current Quality Lab.

## 5. Fit against the hackathon themes

| Theme line | What we have | Gap | Cheapest credible close |
|---|---|---|---|
| Transformer model for port dwell from **satellite imagery** and AIS | C4: LightGBM + CQR + survival on GFW/CPA; DINOv2 (a ViT) only in C5 | No satellite in the UI; no transformer in C4 | (a) Satellite panel per Q-15 default: Sentinel-1 thumbnail of the Chattogram anchorage + GFW SAR vessel counts beside the AIS count ("dark ships"). (b) A small time-series transformer (e.g. a pretrained TSFM, zero-shot, D-02) for the queue forecast, kept only if it beats L3 (rule 5) |
| **CV quality inspection** feeding **defective-batch forecasting** | C5: DINOv2 scoring → AQL → beta-binomial lot risk → SPC → order impact | Lot risk is per lot now; no forward forecast view | "Next 10 lots" forecast per line/supplier from the beta-binomial posterior, with bands, on Quality Lab (S) |
| **NLP agent** parsing trade news to **adjust buffer stocks** in real time | C2 + Nexus buffer recommendations every 15 min | Tariff/trade-policy news is only a lexicon class (`TRADE_POLICY_SANCTION`) with a generic prior | Tariff Monitor (§6, F-1) gives this class real numbers |
| **GNN** for N-tier dependencies and hidden SPOFs | C1 analytics (dominators, removal test, LPs) | No GNN at all | GraphSAGE/R-GCN risk scorer or **hidden-link prediction** ("suspected tier-2 supplier", dashed edges) trained on the synthetic world, CPU inference; adopt only if it beats the baseline, otherwise show it as an honest experiment (Q-12 answer allows this) |
| **RL agent** for multi-objective routing (carbon vs speed) | C3 Pareto set (time, cost, CO2e) | No RL (Q-14 default) | Preference-conditioned tabular Q-learning or a contextual bandit over (departure hour, mode chain) on the C3 simulator; report regret vs the Pareto planner on ≥ 50 held-out scenarios (C3-AC07). Mark "experimental" |

The three RL/GNN/transformer items are where a judge reading the theme list will look first.
Each can be a small, honest experiment rather than a replacement.

## 6. Proposed features (interesting, useful, not too complex)

Scored on judge impact, link to what exists, and effort. Effort: S ≤ 1 day, M 2–3 days.

| ID | Feature | Why judges care | Builds on | Effort |
|---|---|---|---|---|
| **F-1** | **Tariff & Trade-Policy Monitor** (requested): tariff matrix by product × market × origin, change feed from official sources, landed-duty exposure per order, Bangladesh **LDC-graduation cliff** scenario, **rules-of-origin check** from the BOM | Bangladesh's LDC graduation is scheduled for 24 Nov 2026 *(verify)*, which ends duty-free access over transition periods; US surcharges on Bangladesh changed three times in 2025 (seen in USITC HTS today). Very topical, very visual | `trade_flow`, industry-pack HS6 codes, BOM origins, C2 `TRADE_POLICY_SANCTION`, Nexus recommendations | M (plan in `C6-tariff-monitor-plan.md`) |
| F-2 | **Satellite "dark ship" panel** on Ports & Vessels | Directly answers the satellite theme line | Existing CDSE and GFW SAR connectors | S–M |
| F-3 | **Disruption-aware routing** (fixes G-1) | Makes the hero story consistent across pages | C2 events, C4 waits, C3 graph | S–M |
| F-4 | **Hidden-link GNN** ("suspected tier-2 supplier" dashed edges with a probability) | The GNN theme line; looks good on the Sigma graph | C1 graph, synthetic world ground truth | M |
| F-5 | **Shipment carbon passport**: per-shipment ISO 14083 CO2e statement (PDF) with the factor rows cited; EU buyers ask for this | Green-manufacturing overlap; uses numbers we already compute | C3 CO2e per leg, Studio PDF export | S |
| F-6 | **Defective-batch forecast** strip on Quality Lab | The CV→forecasting theme line | C5 beta-binomial posterior | S |
| F-7 | **Text-prompted zero-shot inspection** (from the teammate PR, ported) | Upload any product photo and describe the defect | C5 inspections endpoint | S–M |
| F-8 | RL departure/mode experiment | The RL theme line | C3 Monte Carlo simulator | M |

Recommended order for the time left: **F-3 (consistency) → F-1 (requested, new) → F-2 → F-4 or
F-8 → F-5/F-6 as polish.** F-3 first because the golden path already claims it.

Not proposed: an "Ask Nexus" copilot (the user declined it, Q-17 → U-09); MarineTraffic (paid,
D-07).

## 7. The organisers' suggestions (`suggestions.txt`), checked

Four tracks are listed; ours is **Supply Chain Nexus** ("Cost, resilience and speed gains;
forecasting + optimisation + agents").

| Example prompt (SC Nexus track) | Covered by | Verdict |
|---|---|---|
| Transformer for port dwell from satellite + AIS | C4 (no satellite, no transformer) | Partial; see §5 |
| GNN for N-tier SPOFs | C1 analytics | Partial; analytics are stronger evidence than a GNN on synthetic data, but add F-4 for the theme |
| NLP agent adjusting buffer stocks | C2 + Nexus | **Covered** |
| RL routing, carbon vs speed | C3 Pareto | Partial; F-8 |
| CV quality inspection → defective-batch forecasting | C5 | Mostly covered; F-6 |

| Suggested data source | Status here |
|---|---|
| MarineTraffic API | **Excluded**: paid (D-07). We use aisstream, GFW, DMA and CPA instead |
| World Bank Open Data | Used (DS-TRADE-03) |
| OpenStreetMap | Used (C3 graph, Geofabrik) |
| GDELT | Used (DS-NEWS-02) |
| Kaggle supply-chain datasets | Not used. A demand-forecasting baseline is missing everywhere (buffers use synthetic order demand); a Kaggle demand set could train one, but it would not be Bangladesh data. Low priority |

Ideas from the other tracks that fit our corridor without leaving scope:

- *Green Manufacturing* "trace the carbon footprint across Tier-1/Tier-2" → combine C1's graph
  with C3's CO2e per leg: a per-product footprint roll-up (F-5 extension).
- *Factory Brain / Predictive Plant* RAG over manuals, acoustic anomaly (MIMII), digital twins →
  out of scope for a supply-chain platform; skip.
- *Green Manufacturing* "Climate TRACE facility emissions" → could benchmark ports' emissions;
  low priority.

External idea (not in the file): **tariffs and rules of origin** (F-1). Of all supply-chain
levers in 2025–26, trade policy moved landed cost the most for Bangladeshi garments, and the
LDC graduation makes it a Bangladesh-specific story no other team is likely to tell.

## 8. Questions for the user (batched, per `AGENTS.md` §7)

| Q-ID | Context | Options | Recommendation |
|---|---|---|---|
| Q-18 | F-1 is a new capability. Where does it live? | (a) new package `packages/c6_tariffs` + ADR-021 · (b) inside `nexus` · (c) inside `connectors` + API only | (a): it keeps pipelines independent (rule 6) |
| Q-19 | Order for the remaining time | F-3 → F-1 → F-2 → F-4/F-8 · F-1 first · other | F-3 first, F-1 second |
| Q-20 | Teammate PR #1 | Port the idea into current C5 (F-7) · ask the teammate to rebase · close it | Port the idea; credit the teammate |
| Q-21 | Tariff markets for the demo | US, EU, UK (+ Canada, Japan later) | US, EU, UK: the probed sources cover them |

While waiting: nothing here blocks F-3 or the docs; F-1's probes and plan are done.
