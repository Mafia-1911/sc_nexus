# Model card: Nexus recommendation engine (`nx-buffer-0.1.0`)

Capability: Nexus layer (`docs/brief/08-nexus-layer.md` §4, NX-R04, NX-AC04). Code:
`packages/nexus/src/cportal_nexus/buffer.py` (disruption actions), `alerts.py` (hazard-feed
alerts), C5's `impact.py` (quality actions). Nothing is auto-executed: every action is proposed,
then accepted or dismissed with feedback (K-04).

## Rules

| Action | Trigger | Cost | Benefit | Source |
|---|---|---|---|---|
| `increase_safety_stock` | an open disruption alert whose C1 what-if makes orders late | extra units × value × 25 %/yr holding × carry days | confidence × late revenue × 15 % lateness cost | buffer maths SS = z·√(L̄σd² + d̄²σL²) |
| `pull_forward_po` | same alert, inputs exposed to the hit node (at the supplier, on its route, or upstream via C1 `input_deps`) | units × value × (5 % rush premium + holding × days pulled forward / 365) | as above × share that can still beat the event (days until it starts ÷ days the order needs) | proposed only when expected value > 0 |
| `rework`, `replace_production`, `expedite_air`, `notify_customer` | a failed AQL lot whose order is at risk (C5) | C5 priors | C5 priors | `config/priors/c5.yaml` |

Confidence = the Nexus **fused** confidence (08 §3) when there is one, else the event's.
Evidence = the event, the fusion row, and every corroborating event. Expected value = benefit −
cost; the API returns `expected_value_usd` and ranks an event's actions by it. All rates are
estimates (A-090, A-095).

**Hazard alerts (A-096).** C2 alerts on news only, so forecasts never reached the engine. Nexus
raises a `disruption` alert for a GDACS/PortWatch event that is known as of the scope's `now`,
touches a LOCODE, and passes C2's thresholds on severity (or its type prior) and fused
confidence; one per GDACS id.

## Golden path (hero scenario, as of 2026-10-26)

| Alert | Action | Expected value | Confidence |
|---|---|---|---|
| Tropical Cyclone SYN-01 (forecast, PortWatch) | raise the buffer (2.1 days of cover, knit and denim fabric) | US$69.1K | 0.95 |
| Tropical Cyclone SYN-01 | pull the next PO forward 2 days (3 fabric lines, incl. Mill X) — 5–6 % can beat it | US$3.8K | 0.95 |
| Chattogram port suspends cargo handling (news) | raise the buffer | US$62.3K | 0.86 |
| Failed garment lots (Quality Lab) | rework, replace, air, notify | C5 | C5 |

NX-AC04 (≥ 3 types in the golden path, each with expected value, confidence and evidence): met
(safety stock, pull-forward, rework, replacement, air, buyer notice).

## Limits (honest)

- Benefits are not netted across alternatives: safety stock and pull-forward address the same
  late orders, so their benefits must not be added (the UI shows them as alternatives).
- A pull-forward 1.2 days before a 22-day-lead order mostly cannot beat the event (5–6 %); it is
  still worth it only because the rush and holding cost of 2 days of cover is small. The rush
  premium is an estimate.
- No `reroute` / `mode_shift` / `dual_source` actions yet; C3's Route Planner shows the routing
  options, but the engine does not propose them.
- Not evaluated against outcomes: the useful rate (K-04) needs accept/dismiss data or a backtest.
