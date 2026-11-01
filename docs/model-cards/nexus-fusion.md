# Model card: Nexus evidence fusion (`nx-fusion-0.1.0`)

Capability: Nexus layer (`docs/brief/08-nexus-layer.md` §3, NX-R03, NX-AC03). Code:
`packages/nexus/src/cportal_nexus/fusion.py`; weights `config/priors/fusion.yaml` (A-093).
Output: one `prediction` row per event and scope (capability `nexus`, target `event_confidence`):
the real world (now = the clock) and each scenario (now = its start). Shown on the Disruption Radar.

## Method

    logit(conf) = logit(base) + prior(type) + Σ weight[kind] · strength

| Part | Value (estimates) | Notes |
|---|---|---|
| base | C2's news confidence (noisy-OR over outlets, single-source cap), or a hazard feed's reliability | keeps C2's own calibration when nothing else is known |
| hazard | weight 1.6; strength by GDACS alert: green 0.3, orange 0.7, red 1.0 | GDACS (DS-WX-02) and PortWatch (DS-PORT-01), one per GDACS id; related type, ≤ 300 km or shared LOCODE, starts ≤ 96 h apart |
| news (for a hazard event) | weight 1.2; strength = the news event's confidence | news the hazard explains |
| physical | weight 2.0; strength = drop in departures at the LOCODE (≥ 50 % in 24 h vs 14-day mean) | port calls available before `now`; absence is a check, not counter-evidence |
| official | weight 2.5 | no official notices feed yet |
| NX-R03 | one outlet with reliability ≤ 0.6 and no hazard/physical/official signal → ≤ 0.5 | unit-tested |

Only facts available at `now` count (`available_at`): GDACS's own SYN-01 episode is published at
07:00 on the 26th, after the hero scenario's start, so PortWatch's copy is what corroborates it.

## Results

| Scope | Events | Corroborated by another kind |
|---|---|---|
| real (2026-11-01) | 297 | 0 |
| baseline | 288 | 0 |
| cyclone + supplier delay | 290 | 1 (two events corroborate each other) |

Hero: "Chattogram port suspends cargo handling" 0.665 → **0.859** (hazard: Tropical Cyclone SYN-01,
orange, +1.12 log-odds); "Tropical Cyclone SYN-01" 0.90 → **0.952** (news, +0.80). Physical check
at the scenario's start: 15 departures in 24 h vs 24 expected, below the 50 % drop (the closure
starts later). NX-AC03 (≥ 2 kinds of evidence: news + hazard feed): met. All three scopes fuse in
≈ 1 s; door ETA holds now use the fused confidence.

## Limits (honest)

- Weights are hand-set, not tuned: no labelled set of corroborated vs false events yet (the
  backtest, 08 §6, is where they get tuned).
- No real-world event is corroborated today: real GDACS events are far from or unrelated to the
  current news; the rules are deliberately strict (type, distance, time).
- Physical evidence uses departures only; anchorage queue z-scores, AIS-dark gaps and SAR counts
  are not wired yet. Departures from GFW (real scope) end at 2026-09-07, so the real scope has no
  physical signal.
- Fusion links events; it does not merge them. The news event and the hazard event stay two rows.
- Buffer recommendations still show C2's news confidence (to switch with the recommendation engine).
