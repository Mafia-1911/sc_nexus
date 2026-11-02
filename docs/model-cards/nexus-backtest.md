# Model card: Nexus backtest (`nx-backtest-0.1.0`)

Capability: Nexus layer, "time machine" (`docs/brief/08-nexus-layer.md` §6, NX-AC06; K-03, K-04).
Code: `packages/nexus/src/cportal_nexus/backtest.py`; run `uv run nexus backtest` → raw report
`nexus-backtest.json`; settings `config/priors/nexus.yaml` (`backtest`, A-099). Data: real GFW
port visits at Chattogram (DS-AIS-02, **non-commercial**) and real GDACS/PortWatch hazard events.

## Method

- **Ground truth:** disruption episodes in the gateway's daily departures: a day at ≤ 50 % of the
  trailing 14-day median (median ≥ 5); disrupted days ≤ 1 day apart merge; the worst day is the
  peak. These are the port-data facts the brief's K-03 means by "peak visibility in port data".
- **Alerts:** hazard-feed events (GDACS, PortWatch) the Nexus alert rule would have raised: the
  gateway's LOCODE or a centroid ≤ 300 km away, C2's severity and confidence thresholds, the
  hazard still current (started ≤ 10 days before it became available), at its `available_at`;
  one per GDACS id (the first feed to publish it).
- **Matching:** an alert matches an episode starting 1 day before to 7 days after it.
  **K-03** = hours from the alert to the episode's worst day (mid-day). **K-04** = matched alerts
  ÷ alerts. Misses (episodes without an alert) get context labels (Eid, the 2024 unrest, any
  hazard in Bangladesh up to 7 days before, at any distance) that explain but never score.
- Not used: news. GDELT coverage in this database starts in October 2026, so the backtest scores
  the hazard-feed half of Nexus only; thresholds were set before looking at the result.

## Results (2023-01-01 → 2026-10-22, 1391 days, 27,292 departures, 19.6 a day)

| Metric | Value |
|---|---|
| Alerts the rule would have raised | 7 |
| Port-data disruption episodes | 28 |
| **K-04 precision** (alerts followed by a disruption) | **0.43** (3 of 7) |
| Recall (episodes with an alert before them) | 0.07 (2 of 28) |
| **K-03 lead time** (first alert → worst day, per disruption) | **median 43.5 h** (range 34–53 h, n 2) |
| Misses with a context label | 10 of 26 |

Matched (true warnings):

| Alert | Known at | Episode starts | Worst day | Lead |
|---|---|---|---|---|
| Flood in Bangladesh, India, Myanmar | 2023-05-13 02:00 UTC | 2023-05-14 | 2023-05-14 (28% of normal) | **34 h** |
| Tropical Cyclone HAMOON-23 | 2023-10-23 07:00 UTC | 2023-10-25 | 2023-10-25 (50% of normal) | **53 h** |
| Flood in Bangladesh | 2023-10-24 02:00 UTC | 2023-10-25 | 2023-10-25 (50% of normal) | **34 h** |

False alarms (no port disruption followed):

| Alert | Known | Distance |
|---|---|---|
| Tropical Cyclone FOUR-23 | 2023-07-31 | 151 km |
| Tropical Cyclone MIDHILI-23 | 2023-11-16 | 117 km |
| Earthquake in Bangladesh | 2025-11-21 | 204 km |
| Earthquake in Bangladesh | 2026-02-27 | 275 km |

Misses with context:

| Episode | Departures vs normal | Context |
|---|---|---|
| 2023-04-22 | 7 vs 20.5 (34%) | Eid al-Fitr (2023-04-22) |
| 2023-06-30 | 8 vs 19.0 (42%) | Eid al-Adha (2023-06-29) |
| 2024-04-11 | 5 vs 21.0 (24%) | Eid al-Fitr (2024-04-11) |
| 2024-04-14 | 10 vs 20.5 (49%) | Eid al-Fitr (2024-04-11) |
| 2024-05-28 | 6 vs 18.5 (32%) | Tropical Cyclone REMAL-24 at 357 km |
| 2024-06-17 | 6 vs 18.5 (32%) | Eid al-Adha (2024-06-17) |
| 2024-07-23 | 7 vs 18.0 (39%) | July–August 2024 unrest (2024-07-18) |
| 2025-03-31 → 2025-04-01 | 7 vs 21.5 (33%) | Eid al-Fitr (2025-03-31) |
| 2025-06-07 → 2025-06-08 | 5 vs 19.5 (29%) | Eid al-Adha (2025-06-07) |
| 2026-03-21 | 7 vs 18.0 (39%) | Eid al-Fitr (2026-03-21) |

Unexplained misses (16): 2023-05-04 (49%), 2023-09-20 (47%), 2024-04-02 (49%), 2024-04-21 (41%), 2024-05-01 (47%), 2024-05-06 (41%), 2024-07-01 (40%), 2024-09-09 (43%), 2024-09-13 (17%), 2025-05-30 (40%), 2025-06-18 (38%), 2025-07-26 (44%), 2025-08-21 (27%), 2025-10-31 (49%), 2026-06-23 (49%), 2026-07-08 (19%).

## Reading it (honest)

- When a hazard Nexus alerts on hits Chattogram, the first warning comes **≈ 1.5–2 days before
  the worst day** (May 2023 flood: 34 h; Hamoon 2023: 53 h, with its flood alert a day later).
  That is the value of the hazard feeds.
- **Precision 0.43:** two cyclones that turned away and two earthquakes did not stall the port.
  Earthquakes are probably the wrong type to alert on for a port; that change is a decision, not
  made here.
- **Recall is low (0.07) by design of the ground truth:** most departure drops are not hazards:
  eight coincide with Eid, one with the 2024 unrest (no feed covers either; a holiday calendar and
  news history would), one is Cyclone Remal, which the 300 km rule excluded (357 km). The
  unexplained single-day drops may include AIS coverage gaps in GFW data rather than real stops.
- Two warned disruptions is a small sample: treat the lead time as an indication, not an estimate.
- Fixed while writing this card: two alerts before one disruption (Hamoon and its flood) were
  counted as two warned episodes; recall and K-03 now count each disruption once (first alert).
