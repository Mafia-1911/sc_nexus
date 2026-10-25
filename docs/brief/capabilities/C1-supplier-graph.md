# C1 · Supplier intelligence: risk graph

**TL;DR.** Build a heterogeneous graph of suppliers, factories, ports, warehouses, customers and products, as a realistic garment and pharma network on real Bangladeshi infrastructure. Find **single points of failure** with dominator analysis, downstream dependency counts, concentration measures, centralities, and **time-to-survive (TTS) vs time-to-recover (TTR)**. Then simulate "what if node X is unavailable for N days" with a cascade simulator. Analytics and simulation are the Must. A **GNN** is a Should or Stretch: it may replace the tabular baseline only if it beats it on held-out data. Build order: 1 of 5. Depends on: core, sim world. Feeds: C2 (entity linking targets), NX (impact, scenarios), C3 (mitigation lanes).

## 1. Job to be done

- **C1-R01** As a garment logistics manager, I see which upstream suppliers and ports most of my products and open orders depend on, ranked and explained.
- **C1-R02** As a pharma planner, I simulate "API supplier X unavailable for 21 days" and see which SKUs stock out and when, with TTS vs TTR.
- **C1-R03** As an executive, I get the top single points of failure with suggested mitigations (dual-source, buffer, alternative port or lane).
- **C1-R04** As a user, I see risk scores with their drivers, not bare numbers.

## 2. Hackathon scope

- **Must:** the graph model and builder; analytics (dominators, downstream count and value, HHI, betweenness and PageRank); TTS/TTR via LP; a deterministic what-if cascade; the graph and geo UI with a what-if panel; a tabular risk score (LightGBM or a transparent weighted score) with SHAP drivers.
- **Should:** Monte Carlo what-if (P50/P90 impact); C2 events and C5 quality feeding into risk; validation of the GNN pipeline on **SupplyGraph** (real Bangladesh FMCG data).
- **Stretch:** heterogeneous-GNN risk scoring; a GNN **surrogate** of the cascade simulator (instant what-ifs); **hidden-link prediction** (likely tier-2 suppliers, shown as dashed "suspected" edges).

## 3. Inputs

| Need | Source | Mode |
|---|---|---|
| Ports, ICDs, EPZ locations | DS-PORT-04/05/06, DS-GEO-02 | real |
| Factories (positions, cluster density) | DS-SUP-01 (Open Supply Hub download), with names per Q-05 | real locations; **fictional firms** for simulated attributes |
| Tier-2/3 flows (country × HS shares) | DS-TRADE-01/02 (Comtrade, BACI) | real, aggregated |
| Country risk, hazard exposure | DS-RISK-01/02, DS-WX-03 (cyclone tracks) | real |
| Pharma compliance signals | DS-PHARMA-01/02/03 | real (fuzzy-matched to *fictional* suppliers only by country/product pattern; never relabel real firms) |
| Delivery performance | DS-SUP-03 (DataCo) for calibration; synthetic OTIF | synthetic, calibrated |
| Supply edges, BOMs, capacities, inventories, orders | `sim/world.py` | synthetic |
| Real temporal graph for method validation | DS-SUP-02 (SupplyGraph) | real |

## 4. Output contract

- `graph_metrics(node_id, as_of, downstream_products, downstream_open_order_value_usd, dominated_products[], betweenness, pagerank_rev, hhi_inputs, single_sourced_inputs[], tts_d, ttr_d, performance_impact, risk_score, risk_band, risk_drivers jsonb, model_version)`
- `whatif_result(scenario_id, disrupted[], duration_d, capacity_pct, mc_runs, timeline jsonb, impacted_orders[], revenue_at_risk_usd_p50/p90, first_impact_d, recovery_d)`
- Events: emits `prediction.created` (risk), `scenario.run_completed`. Consumes `disruption.*` and `batch.status_changed` to refresh risk.

## 5. Method ladder

| Level | Method | Notes |
|---|---|---|
| L0 | **Structural analytics** (NetworkX): downstream reachability weighted by open-order value; **immediate dominators** on the flow graph from a super-source to each product sink (a dominator is a true single point of failure); supplier concentration HHI per input; country concentration; betweenness (flow-weighted) and PageRank on the reversed graph | Fast, explainable, always on |
| L0 | **TTS/TTR** (Simchi-Levi et al. risk-exposure method): for each node *j*, solve an LP (HiGHS via `scipy.optimize.linprog` or PuLP) giving the maximum time the network meets demand with *j* down (TTS), and the lost demand over *j*'s TTR (performance impact). TTR comes from priors per facility type, refined by C2 events | Flag nodes where **TTS < TTR** |
| L0 | **Cascade simulator** (daily steps): disrupt nodes or reduce capacity; propagate shortages through BOM and lanes, respecting inventory, lead times, alternative sources and capacity; record time-to-impact per order | The core of the what-if |
| L1 | **Risk score:** LightGBM (or a transparent weighted score if labels are thin) on country risk, hazard exposure, compliance events, OTIF history, C5 defect rate, C2 event counts and severity, and graph features. Labels: simulator-derived propensity plus real-proxy labels where available. SHAP drivers | The baseline every GNN must beat |
| L1 | **Monte Carlo** over disruption duration and lead-time noise (worker job) | P50/P90 impact |
| L2 | **Heterogeneous GNN** (PyG): `HGTConv` or R-GCN, or GraphSAGE with `to_hetero`, for node risk classification. Same features as L1 plus learned structure. Train in a Kaggle notebook; CPU inference in PyTorch (graph ≤ ~5k nodes) | Adopt only if PR-AUC and calibration beat L1 on held-out nodes and time |
| L3 | **GNN surrogate** of the simulator: train on thousands of random disruption sets; it predicts per-node impact instantly. Validate MAE vs the simulator. Used to scan every single-node disruption in < 1 s | Innovation; flag as approximate |
| L3 | **Hidden-link prediction** (GraphSAGE / R-GCN with a DistMult decoder; cf. Kosasih & Brintrup 2022): suggests likely tier-2 suppliers from trade-flow priors, geography and co-supplier patterns | Never merged into "known" edges; UI shows them dashed with confidence |
| L3 | **SupplyGraph validation:** run the GNN pipeline on the real Bangladeshi FMCG graph (its published tasks) to show the methods work on real data | Credibility for judges |

## 6. Models and libraries

NetworkX (dominators, centralities), igraph (speed), SciPy/HiGHS or PuLP (LP), LightGBM + SHAP, PyTorch Geometric (HGT, R-GCN, SAGE, `torch_geometric.explain` for GNNExplainer), graphology export for Sigma.js. Notebooks: `notebooks/c1_gnn.ipynb` (Kaggle GPU optional; a small graph trains on CPU too).

## 7. Evaluation and acceptance

| ID | Criterion |
|---|---|
| C1-AC01 | The seeded graph (≥ 150 nodes, ≥ 600 edges, garment and pharma) loads in the UI in < 2 s, with network and geo views |
| C1-AC02 | **Planted single points of failure** in the synthetic world appear in the top 10 of the criticality ranking (recall ≥ 0.9 over 5 seeds) |
| C1-AC03 | TTS and TTR are computed for every supplier node; the TTS < TTR list is shown with drivers |
| C1-AC04 | A deterministic single-node what-if returns in < 2 s; Monte Carlo (200 runs) completes as a job in < 15 s; results are reproducible by seed |
| C1-AC05 | The risk score has SHAP drivers per node. If the GNN is attempted: report PR-AUC and calibration vs L1 on the same split, and adopt only if better (ADR) |
| C1-AC06 | C2 events linked to a node change its risk and what-if defaults within one refresh cycle |

## 8. API

`GET /graph?view=network|geo&industry=&cluster=` · `GET /graph/nodes/{id}` · `GET /graph/critical?metric=dominance|downstream|tts_gap&limit=20` · `POST /graph/whatif` (body: nodes, duration_d, capacity_pct, mc_runs; returns 202 + job_id if MC) · `GET /graph/whatif/{id}` · `GET /graph/suggested-links` (stretch)

## 9. UI

The Supplier Network page (`05-ui-design.md` §4, §6): graph ↔ map toggle, criticality leaderboard, node drawer (risk with drivers, dependencies, events, quality), and a what-if panel with ripple animation, TTS vs TTR bars, orders-at-risk table and **mitigation suggestions** (recommendation cards via NX).

## 10. Integration hooks

- **C2:** entity-linking targets (organisations, facilities, ports, products); events raise risk and seed what-ifs.
- **C4:** port dwell distributions become lane lead-time distributions.
- **C3:** alternative lanes and modes as mitigation options.
- **C5:** supplier and plant quality scores.
- **NX:** cascade engine for scenarios; impact for recommendations.

## 11. Risks and guardrails

- **Defamation or misleading output:** simulated risk only on fictional firms (Q-05).
- **False precision:** show intervals, and label TTR priors as assumptions.
- **GNN for show:** keep it only if it wins (AGENTS.md §4.5).
- **Graph realism:** calibrate shares to Comtrade/BACI, and document the assumptions in the world generator's README.
- Open questions: Q-05, Q-12.
