# ADR-018: C3 on our own OSM road graph, Monte Carlo mode chains and a Pareto filter

Status: accepted   Date: 2026-10-27

**Context:** C3 must return 3–7 non-dominated plans (time P50/P90, cost, CO2e) with an on-time
probability in < 5 s on a CPU laptop, for road, rail (Kamalapur) and barge (Pangaon), with truck
bans and synthetic timetables, and without live traffic (C3 §2, §11). ADR-007 put Valhalla off
until a realism gap is measured; ADR-013 chose local OSM processing over Overpass.

**Decision:**
- **Graph:** `osmium` extracts motorway–secondary ways inside the corridor box from the Geofabrik
  extract into a `road_edge` table (junction to junction). The API and worker build a NetworkX
  graph from it once per process (reloaded when the table changes).
- **Time:** free-flow truck speed per road class × one ORS-fitted multiplier × an hour-of-day
  factor (a Dhaka profile within 18 km of the centre); the DMP heavy-vehicle ban (user-verified,
  08:00–20:00, central corridors as an 8 km circle) makes trucks wait at the zone edge.
  Lognormal noise per road leg, dwell per transfer, waits for the next non-cancelled departure.
- **Plans:** fastest, shortest and a detour (fastest edges penalised ×1.6) by road; from
  Chattogram also rail and barge chains; Monte Carlo (300 draws) → P50/P90 and P(on time);
  cost from cited tariffs; CO2e from the DESNZ row per mode; Pareto ranks on (P50, cost, CO2e);
  a departure sweep (every 3 h over 48 h) for the top three.

**Alternatives considered:** Valhalla (another service; ADR-007 says measure first); OSMnx
(pulls the whole country into memory); multi-objective label setting (overkill for a handful of
mode chains); ORS for production routing (quota, and C3 §3 keeps it for calibration only).

**Consequences:** + offline, fast, explainable, every number traceable. − Speeds and timetables
are modelled; tertiary roads are left out (RAM); the barge CO2e factor is a sea-container proxy.
