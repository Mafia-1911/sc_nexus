# ADR-007: Corridor graph from the Geofabrik extract first; Valhalla only on a measured gap

Status: accepted   Date: 2026-10-26

**Context:** C3 needs road, rail and barge legs from Chattogram to the Dhaka-area clusters. ORS
(DS-GEO-03, verified at G0) gives 244.8 km Chattogram port → Kamalapur ICD but free-flow
durations far below real truck times.

**Decision:** Build the multimodal corridor graph from the Geofabrik PBF (DS-GEO-01) with
OSMnx/pyrosm and igraph, plus rail and barge service timetables (synthetic until real data).
ORS validates distances and route shapes on a small set of OD pairs within its rate limit;
durations are modelled from congestion priors, not taken from ORS.

**Alternatives considered:** Valhalla/OSRM servers (another service; only if a realism gap is
measured); ORS as the router (rate limits, free-flow times).

**Consequences:** + offline routing. − Travel-time calibration is our job (M5).
