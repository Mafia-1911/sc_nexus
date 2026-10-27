# Model card: C4 port dwell (`c4-baseline-0.1.0`), Chattogram

Capability: C4 port dwell prediction. Code: `packages/c4_port_dwell`. Registered on: 2026-10-27
(`model_version` rows `c4-* (BDCGP)`). Design: ADR-019. Raw report: `c4-eval-BDCGP.json`.
Licence: code only; **trained on Global Fishing Watch data (CC BY-NC 4.0, non-commercial)**.

## Data

| | |
|---|---|
| Labels | GFW port visits at Chattogram (DS-AIS-02), backfilled 2023-01-01 → 2026-10-23: 27,315 calls; 26,008 kept |
| Dropped | 658 laid up (> 60 d), 317 cut by the window start, 205 low confidence (< 3), 104 shorter than 2 h, 23 still active |
| Target | total dwell, hours (D-04: anchorage wait + berth time). GFW's stops carry no times, so there is no wait/berth split |
| Mix | 18,093 cargo (P50 88 h, P90 302 h), 6,663 unknown type, 1,112 fishing, 123 passenger, 17 tanker |
| Queue series | GFW 4Wings presence: vessels ≥ 1 h in the outer anchorage per day, 1,392 days (51–169, mean 118) |

## Models

| Level | Method | Baseline it must beat |
|---|---|---|
| L1 dwell at arrival | 3 LightGBM quantile models (P10, P50, P90) on log hours; MAPIE conformalises the P10–P90 band (CQR, prefit); TreeSHAP drivers | L0: empirical P10/P50/P90 by type × flag × month |
| L2 remaining time | Random survival forest (100 trees, 2 h bins, 10k calls); remaining quantiles from S(e + r)/S(e) | Kaplan–Meier, same conditioning |
| L3 anchorage queue | Direct LightGBM P50 per horizon (1–14 d) on lags, means, weekday, month; P10/P90 from residuals on a 90-day calibration window | Seasonal naive (last week) with residual quantiles |

Features (point-in-time, observer lag 24 h): vessels in port and cargo vessels in port, their mean
time in port, arrivals and departures over 1–7 days and their ratio, typical stay over the last
14 days, anchorage presence, ship type, Bangladesh flag, the vessel's calls in the last year, its
usual stay and hours since its last call, month, weekday, arrival hour.

## Evaluation (time split: train → 2026-04-11, validate → 2026-05-26, gap, test 2026-07-10 → 09-08)

| Check | Result | Criterion |
|---|---|---|
| L1 vs L0, cargo vessels (776 test calls) | MAE 75.7 h vs 92.1 h: **17.8 % better**; median APE 0.41 vs 0.57 | C4-AC03: ≥ 15 % — **met for cargo** |
| L1 vs L0, all vessels (1,163) | MAE 89.8 h vs 102.4 h: 12.3 % better | not met for all vessel types (fishing and passenger stays are noisy) |
| 80 % interval coverage, test | 81.3 % all, 83.4 % cargo (median width 267 h / 235 h) | C4-AC04: 75–85 % — **met** |
| L2, test calls | C-index 0.653; integrated Brier 0.162 vs 0.193 (Kaplan–Meier) | C4-AC05: reported |
| L2, vessels still in port after 24 h (1,043) | remaining-time MAE 94.5 h vs 104.6 h (Kaplan–Meier) | better than baseline |
| L3, 7 days ahead, 113 rolling origins | MASE 1.16 vs 1.26, WQL 0.071 vs 0.085 (seasonal naive); 80 % band covers 69 % | C4-AC06: beats naive — **met**; band under-covers |
| Point-in-time features | truncation test at lags 0, 24, 96 h (`test_features_never_read_past_as_of`) | C4-AC07 — **met** |
| Feed latency (cargo MAE) | 0 h: 70.7 · 24 h: 75.7 · 96 h: 78.5 | a live feed is worth ≈ 7 % |

The strongest features are the vessel's own history (usual stay, time since its last call, calls
per year) and the recent typical stay; the queue matters less than expected at this resolution.

## Assumptions and limits

- **No live Chattogram picture.** GFW publishes a visit after it ends; the replay ends 45 days
  before the data so that every shown vessel's outcome is known. A live deployment needs AIS or
  CPA's daily vessel report as the feed (the 24 h lag stands for the latter).
- GFW "visits" include lighterage at anchor (most cargo visits never reach a dock, SC-03) and
  are anchorage-group based; draught, LOA and DWT are not yet features (GFW identity not
  fetched), so the channel limits in `config/priors/c4.yaml` are unused so far.
- Mongla has 806 usable calls: too few for L1; it would fall back to L0.
- The queue fan's 80 % band covers 69 % at 7 days: read it as optimistic.
- Not yet: AIS state machine on DMA data and the GFW cross-check (C4-AC02), weather, tide,
  holidays and C2 events as features, SAR counts (Q-15), a TSFM (Chronos-2) for the queue.
