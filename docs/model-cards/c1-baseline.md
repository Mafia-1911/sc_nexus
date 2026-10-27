# Model card: C1 baseline (`c1-baseline-0.1.0`)

Capability: C1 supplier risk graph. Code: `packages/c1_supplier_graph`. Registered on: 2026-10-27.
Licence: code only (no learned weights); inputs are synthetic (fictional firms at real clusters).

## What it is

No learned model yet. The baseline every later model must beat (AGENTS.md rule 5):

| Part | Method | Output |
|---|---|---|
| Single points of failure | Removal test on the AND/OR supply graph (a plant needs every BOM input; each input from any qualified supplier) | dominated orders and value per node |
| Dependency reach | Exact dependency sets through BOM and routes | downstream orders and value |
| Concentration | HHI per input, single-sourced inputs, sole-source relationships | per node |
| Centrality | Betweenness; PageRank on the reversed value-weighted flow graph | per node |
| TTS / TTR | Simchi-Levi risk-exposure LP (HiGHS): max time demand is met with the node down, using inventory and qualified alternatives' spare capacity; performance impact = value of output lost over TTR | days, US$ |
| What-if | Daily cascade (inventory, transit pipeline, backorders, re-sourcing after a 7-day ramp, gateway closures, hub reroutes); Monte Carlo over duration, delay, transit and ramp | first impact, recovery, late orders, revenue at risk P50/P90 |
| Risk score | 100 × Σ weightᵢ·featureᵢ: dominance 0.30, reach 0.10, TTS gap 0.15, hazard 0.15, lot quality 0.10, linked events 0.20 | 0–100, band, exact Shapley drivers |

## Evaluation (synthetic world v0.2, `tests/test_c1_acceptance.py`)

| Check | Result | Criterion |
|---|---|---|
| Graph size | 151 nodes, 955 supply relationships | C1-AC01: ≥ 150 nodes, ≥ 600 edges |
| Planted sole sources in their industry's top 10 by dominance, seeds 42, 7, 11, 23, 99 | 20 / 20 (recall 1.0); ranks 1–6 | C1-AC02: recall ≥ 0.9 |
| Chattogram gateway ranked first | 5 / 5 seeds | expected structure |
| TTS < TTR for every planted sole source | yes (e.g. Mill X 7.9 d vs 21 d prior) | C1-AC03 |
| Deterministic what-if (Mill X out 21 d) | ≈ 25 ms in the cascade, < 2 s through the API | C1-AC04: < 2 s |
| 200 Monte Carlo runs (Chattogram closed 3 d) | ≈ 11 s, identical by seed | C1-AC04: < 15 s, reproducible |
| Risk drivers sum to score minus the mean | exact (unit test) | C1-AC05 |

There is **no time-based holdout**: the risk score has no outcome labels yet (no real disruptions
of fictional firms), so it is not a calibrated probability. The planted-SPOF recall tests the
structural ranking, not the likelihood side.

## Assumptions (all in `config/priors/c1.yaml`, shown as estimates in the UI)

TTR by node type, transit times, export lead times, the 7-day ramp-up, 25 % catch-up surge, port
clearing at half the closure length, hazard exposure by cluster (ordinal), and the risk weights.
Country risk is left out: the DS-RISK-01 sample is an API error (A-054).

## Limits

- Facility capacity is per product, from current volumes × a 10–60 % headroom; plants have no
  capacity limit beyond their inputs.
- Transshipment hubs are always substitutable; the destination ports are not modelled.
- A plant's own orders are excluded from its dominance (it trivially stops them).
- Synthetic world only; scores must never be attached to real firms (Q-05 guardrail in the API).

## Next (if C1 is deepened)

LightGBM on simulator-derived labels vs this baseline; Monte Carlo in the UI; GNN per Q-12;
hazard from IBTrACS tracks; country risk once WGI is re-probed.
