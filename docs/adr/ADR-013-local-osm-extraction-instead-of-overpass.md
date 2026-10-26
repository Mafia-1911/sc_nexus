# ADR-013: Local OSM extraction instead of Overpass

Status: accepted   Date: 2026-10-26

**Context:** Overpass took 30–114 s per query, returned 502 at capacity and its mirror timed out
(A-014, two strikes). OSM has no anchorage polygons at Chattogram (A-015).

**Decision:** Port zones, ICDs, depots and the road graph come from the Geofabrik Bangladesh PBF
(DS-GEO-01) processed locally (osmium/pyrosm) in M2–M5. Overpass stays a small probe tool.
Anchorage zones come from GFW anchorage cells; berths from the CPA report.

**Alternatives considered:** Overpass in production (fair-use limits, unreliable).

**Consequences:** + offline and reproducible. − A ~360 MB download per refresh.
