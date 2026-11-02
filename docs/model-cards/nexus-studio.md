# Model card: Nexus Scenario Studio (`nx-buffer-0.1.0`)

Capability: Nexus layer (`docs/brief/08-nexus-layer.md` §2, NX-R02, NX-AC05). Code:
`packages/nexus/src/cportal_nexus/studio.py`; priors `config/priors/nexus.yaml` (`studio`,
`reroute`; A-097, A-098). Output: one `scenario_result` row per scenario (capability `nexus`),
served by `GET /scenarios/{key}/results`; page: Scenario Studio (one-page PDF export via print).

## Method

Two policies on the same inputs, as of the scenario's start; deterministic (no sampling):

| Policy | What happens |
|---|---|
| `baseline` | do nothing |
| `nexus_recommended` | accept every proposed action with expected value > 0 |

| KPI | How |
|---|---|
| K-05 orders at risk, production | C1's cascade on the scenario's open disruption alerts (known by `now`), each at its P90 length (`buffer.window`, the same definition the recommendation engine uses); with Nexus, buffer and pull-forward units (× feasible share) are added to plant input inventory and the cascade reruns; a rerouted order blocked at the gateway counts as saved with Mongla's feasible share (expected counts) |
| K-05 quality | orders at risk from failed lots (C5); saved with Nexus when the best positive-value option is ready by the order's date |
| K-05 in transit | door-ETA P90 later than due (P(on time) < 0.9); actions do not change transit |
| K-06 OTIF | 1 − (production + quality late) / open orders in C1's horizon |
| K-07 CO2e | inland kg CO2e per TEU of open shipments' road/rail/barge legs (great-circle × detour, DESNZ 2026 via C3), plus what the actions add (air vs sea, DESNZ international freight with RF) |
| Value | lateness cost avoided (Δ revenue at risk × 15 % + C5's own benefit for saved quality orders) − cost of the actions |

## Results (as of 2026-10-26)

| Scenario | Orders at risk, production P90 | Quality | OTIF | Lateness cost avoided | Action cost | Net |
|---|---|---|---|---|---|---|
| baseline | 0 → 0 | 1 → 0 | 99.3 % → 100 % | US$8.2K | US$0.7K | **+US$7.5K** |
| cyclone + supplier delay | 5.0 → 3.8 | 1 → 0 | 95.7 % → 97.3 % (+1.6 pts) | US$107.8K | US$9.4K | **+US$98.4K** |

Hero: revenue at risk (P90) US$1.87M → US$1.20M; at the P50 length, 2.0 → 0.8 orders late.
Actions: two reroutes via Mongla (both alerts), one rework. CO2e added by actions: 0 (no air
freight chosen; rework saves the quality order). Inland CO2e ≈ 54 kg per TEU in both columns.
In transit: 53 orders at risk in both columns (the synthetic due-date artefact: ≈ 5 h of slack).

## Limits (honest)

- **Found while building it (fixed):** the buffer rule sized input stock for every late order,
  but C1 shows the hero's late orders are finished goods stuck at the shut port (cause
  `gateway`); stock cannot help those. Buffer and pull-forward now only address input shortages,
  and gateway-blocked orders get a reroute (A-098). The hero's golden-path step 5 therefore shows
  "export via Mongla", not "raise safety stock".
- Two alerts on the same port (news + hazard) propose overlapping reroutes; both costs count,
  the benefit counts once per order (conservative).
- Reroute feasible share (60 %), extra cost (US$250/TEU) and extra days (2) are estimates;
  Mongla's inland CO2e change is not modelled; K-07 does not move until mode-shift actions exist.
- No outcome validation: the counterfactual is the platform's own models (C1 cascade, C5 options).
