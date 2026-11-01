# Model card: Nexus door ETA (`nx-door-eta-0.1.0`)

Capability: Nexus layer, shipment tracker (`docs/brief/08-nexus-layer.md` §1, NX-R01, NX-AC02).
Code: `packages/nexus/src/cportal_nexus/door_eta.py` (pure Monte Carlo) and `tracker.py` (inputs
from the database, outputs to `prediction` and `shipment.predicted_eta_p50/p90`). Priors:
`config/priors/nexus.yaml`. Registered as `model_version` `nexus-door-eta-montecarlo` per scenario.
Licence: code only; inputs inherit their sources' licences (C4 uses GFW, non-commercial).

## Method

1,000 seeded samples per open shipment (in transit or planned), walking the remaining legs:

| Part | How | Source |
|---|---|---|
| Moving time | planned duration × lognormal(0, σ by mode): road 0.25, rail 0.35, barge 0.30, sea 0.12, air 0.10 | estimates (A-092); sea ≈ liner schedule reliability of roughly 50–55 % on time |
| Leg under way | only the remaining planned time is uncertain; a late departure carries over | — |
| Schedules | a leg never leaves before its planned departure; lateness carries forward | — |
| Chattogram vessel stay | deviation from median of C4 port-call predictions (last 60 days; 1,129 in the pool), sampled from each prediction's P10/P50/P90 | C4 (`c4-port-dwell`) |
| Chattogram container dwell | yard + customs, P50 96 h, P90 192 h, deviation from P50 | estimate: C1's 4-day gateway dwell; P90 = 2× (A-092) |
| Disruptions | stoppage-type events (capacity ≤ 20 %: port suspension, cyclone, fire, strike) at a leg's LOCODE pause the stay there; applied with probability = event confidence; duration from the event or its type prior | C2 events, `disruptions.yaml` |
| On time | P(door ≤ 23:59 Dhaka on the earliest linked order's due date) | orders |

Each disruption draws from its own random stream (common random numbers), so with-versus-without
comparisons show only the event's effect. Drivers = mean extra hours vs plan by cause; the
residual (schedules absorbing early arrivals, a late start) is "schedules and connections".

## Results (synthetic world 0.3.0, as of 2026-10-26)

| Scenario | Open shipments | Mean P(on time) | Median P50 − plan | Mean P90 − P50 |
|---|---|---|---|---|
| baseline | 53 | 0.34 | +11 h | 115 h |
| cyclone + supplier delay | 54 | 0.33 | +11 h | 121 h |

With the cyclone, shipments passing Chattogram during the suspension move by up to +26 h (P50) and
+38 h (P90), and their P(on time) drops 3–5 points; the others are unchanged (common random
numbers). Runtime: 107 shipments in ≈ 2.5 s on the CPU (worker job `nexus:door_eta`, every 15 min,
after C2 events and after C4 retrains).

## Limits (honest)

- **Low on-time probabilities are partly an artefact:** the synthetic orders fall due ≈ 5 h after
  the planned delivery, so any realistic spread puts them near a coin flip, and schedules skew
  lateness (early arrivals are absorbed, late ones carry forward).
- Not yet validated against outcomes: there is no time-based holdout of actual door times; the
  backtest (08 §6) will score P50 error and interval coverage.
- C4's port-call pool is real GFW history (to 2026-09-07) and not scenario-aware; a scenario's
  extra congestion reaches the door ETA only through disruption events.
- Holds stop cargo fully; partial-capacity events (congestion, customs slowdowns) are not modelled.
- C2 dates a news-derived event from its publication; "suspends ahead of the cyclone" therefore
  starts early in the model. Evidence fusion (08 §3) is the place to merge it with the hazard feed.
- The container dwell prior is an estimate; a dated Chattogram average should replace it.
