# ADR-009: Synthetic world and Chattogram port DES, calibrated to real marginals

Status: accepted   Date: 2026-10-26

**Context:** aisstream has no Bangladesh coverage; GFW gives real visit labels with a 2–4 day lag;
PortWatch gives daily calls; the CPA berthing report gives real berths, waits and tides. The
M0 twin matched the median dwell but not the tail (p90 182 vs 276 h) or the anchorage
population (29–36 vs 57–81 cargo vessels).

**Decision:** `packages/sim` builds a deterministic world v0 (fictional firms at real clusters,
golden-path structure) and a SimPy port DES with the real CPA berths, tidal windows for deep
vessels, one-way channel slots, lighterage, a lighter/coaster population, and closures with
evacuation. Every vessel draws from its own seeded stream (common random numbers). Source twins
render GFW, PortWatch and aisstream formats from the DES. `make calibrate` compares with real
targets computed from the replay samples and writes CALIBRATION.md: dwell p10/p50/p90 within
13 % and KS D 0.097 vs GFW; anchorage presence 71.7 vs 70.7; arrivals vs PortWatch.

**Alternatives considered:** independent per-visit sampling (the M0 twin: no congestion
dynamics); a queueing formula (no closures, tides or berth identities).

**Consequences:** + C4 gets labelled history with known truth; + scenario differences come from
the disruption alone. − v0 omits Eid slowdowns and yard feedback; the cyclone response is
modest (+3.8 % vessel-hours) until M6 backtests Remal 2024.
