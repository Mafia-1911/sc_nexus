# Model card: C3 routing baseline (`c3-routing-0.1.0`)

Capability: C3 routing optimisation. Code: `packages/c3_routing`. Registered on: 2026-10-27.
Licence: code only (no learned weights). Road network © OpenStreetMap contributors (ODbL, DS-GEO-01,
Geofabrik extract 2026-10-26); emission factors UK DESNZ 2026 (OGL, DS-GEO-05); calibration
reference openrouteservice HGV (DS-GEO-03, validation only, answers cached).

## What it is

No learned model. A transparent planner every later model must beat (AGENTS.md rule 5; ADR-018):

| Part | Method | Output |
|---|---|---|
| Road network | OSM motorway → secondary (and links) inside the corridor bbox, split at junctions: 16,110 directed edges, built in 11 s (2 GB peak) | `road_edge` |
| Road time | Free-flow speed by road class (capped by `maxspeed`) × hour-of-day profile (Dhaka profile within 18 km of the centre), Dhaka local time | hours by departure hour |
| Truck ban | Heavy vehicles wait at the edge of an 8 km circle 08:00–20:00 (user-verified DMP rule, A-070); RMG and pharma exemptions apply only on routes not modelled, so they are listed, not applied | ban wait per leg |
| Candidates | Fastest, shortest and a detour road route; from Chattogram also road + rail via Kamalapur ICD and road + barge via Pangaon ICT | 3–5 chains |
| Uncertainty | Monte Carlo (300 draws): lognormal transfer dwell and service run times, cancelled departures skipped, road time × lognormal(σ 0.22) | P50 / P90, on-time probability |
| Cost | Trailer Tk 130/km (min Tk 6,000) × TEU, reefer ×1.25; rail Tk 28,000/TEU; barge US$190/TEU; ICD handling (press-cited, mixed dates) | BDT and USD |
| CO2e | DESNZ kg CO2e per tonne·km × 10 t per TEU × km, per leg, with the factor row's id, source and year | kg |
| Choice | Pareto rank on (P50 time, cost, CO2e); departure sweep every 3 h over 48 h | ranked plans, "when to leave" strip |

## Evaluation

| Check | Result | Criterion |
|---|---|---|
| Distance vs ORS HGV, 20 corridor pairs | median abs. error 3.2 % | C3-AC01: ≤ 5 % — **met** |
| Free-flow time vs ORS HGV after one scale factor | median abs. error 1.8 % (64 % before; factor 1.64) | C3-AC01: ≤ 15 % — **met** for the route shape; see "speed level" below |
| Chattogram → Gazipur, 2 TEU, 36 h deadline | 5 plans, 4 non-dominated (fastest road, shortest road, rail, barge) in 1.3 s | C3-AC02: ≥ 3 in < 5 s — **met** |
| CO2e traceability | every leg carries its factor row; unit test reproduces factor × t × km | C3-AC03 — **met** |
| On-time probability vs fresh simulated outcomes (deadlines 12–72 h) | max error ≤ 0.1 (`test_on_time_probability_is_calibrated`) | C3-AC04 on synthetic ground truth — **met** |
| C2 closure / C4 congestion changes the plan | not wired yet: C3 does not read C2 events or C4 dwell | C3-AC05 — **not met** |
| Ban respected; same answer for UTC and local inputs | unit test | C3-AC06 — met for the ban; cargo exemptions not applied |

Raw calibration rows: `docs/model-cards/c3-calibration.json` (`uv run c3 calibrate`).

### Speed level (A-075)

ORS agrees with our routes but drives them 1.64× faster: Chattogram → Gazipur in 3.7 h, a 75 km/h
average for a laden truck with no stops. Our class speeds give ≈ 6.2 h free flow (≈ 45 km/h).
The factor is reported and **not applied** until a dated Bangladesh truck time is found (user task);
`uv run c3 calibrate --write` applies it.

## Assumptions (all in `config/priors/c3.yaml`, shown as "modelled" in the UI)

Class speeds, hour profiles, σ, transfer dwell (port gate-out P50 8 h / P90 30 h until C4), rail
and barge timetables (synthetic, calibrated to press reports), cancellation rates, FX 122 BDT/USD,
10 t of cargo per TEU, barge CO2e from a sea-container proxy (A-072). Reefers stay on the road (A-071).

## Limits

- No live traffic: speeds are modelled by class and hour.
- Tertiary and smaller roads are left out, so places off the main network snap to the nearest
  secondary road (Chattogram EPZ: 11 km vs ORS 4 km).
- Mongla has road plans only (no rail or barge service modelled from it).
- The time-based holdout of the brief needs real trip times; there are none yet, so the on-time
  check runs on synthetic ground truth.

## Next (if C3 is deepened)

Read C2 closures and C4 dwell into the plan (C3-AC05); cargo exemptions on the permitted
routes; a measured truck speed level; VRP for multi-drop (C3-AC07 stays off per Q-14).
