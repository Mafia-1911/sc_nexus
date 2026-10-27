# ADR-016: C1 as structural analytics, an LP and a cascade, with a transparent baseline

Status: accepted   Date: 2026-10-27

**Context:** C1 must find single points of failure, compare time to survive with time to recover,
and run what-ifs (C1 §2 Must), in < 2 s interactively on a CPU, with explanations. The world is
synthetic and has no outcome labels.

**Decision:**
- **Dominance by removal test** on the AND/OR graph (a plant needs all BOM inputs, each from any
  qualified supplier). A dominator tree over the facility graph treats every in-edge as OR and
  misses sole sources of a second input. On an OR-only graph the two agree. A node's own orders
  are excluded. Transshipment hubs are substitutable (reroute at a delay); the Chattogram gateway
  is not.
- **TTS/TTR** as the Simchi-Levi LP with SciPy HiGHS; one constraint matrix per graph, bounds per
  node (~17 ms each). TTR from priors by node type, overridden by linked open events.
- **What-if** as a deterministic daily cascade over the part of the network that depends on the
  disrupted nodes (backorders, re-sourcing after a ramp-up, gateway and hub effects), with
  seeded Monte Carlo as a worker job.
- **Risk** as a transparent weighted score whose per-feature contributions are exact Shapley
  values. A learned model (LightGBM, GNN) replaces it only if it wins (rule 5, Q-12).
- **Storage:** `graph_metric` (one row per node and scenario, recomputed by the worker when an
  input fingerprint changes or a `disruption.*` event arrives) and `whatif_result`. Reads come
  from `graph_metric`, inside the 300 ms budget.
- **UI:** Sigma.js with a layered left-to-right layout (05 §6 allows it) instead of ForceAtlas2:
  deterministic and readable for a tiered supply chain; MapLibre for the geo view.

**Alternatives considered:** NetworkX dominators only (wrong under AND); a full MILP for
what-ifs (slower, harder to explain); LightGBM first (no labels); ForceAtlas2 (hairball at 150
nodes with a hub).

**Consequences:** + exact, explainable, fast; planted single points of failure recalled 20/20.
− The cascade is a modelling choice with many assumptions (`config/priors/c1.yaml`); the risk
score is not calibrated to outcomes.
