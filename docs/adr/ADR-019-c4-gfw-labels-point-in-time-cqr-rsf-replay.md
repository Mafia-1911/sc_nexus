# ADR-019: C4 on GFW port-visit labels, point-in-time features, CQR, a survival forest and an honest replay

Status: accepted   Date: 2026-10-27

**Context:** C4 must predict vessel dwell (anchorage wait + berth time, D-04) at Chattogram with
calibrated P10/P50/P90, update the estimate for vessels already waiting, and forecast the
anchorage queue 1–14 days ahead (C4 §2). Live AIS does not reach Bangladesh (U-01); GFW port
visits do (DS-AIS-02, ≈ 2,000 Chattogram visits a quarter, CC BY-NC) but are published only after
a visit ends, with no times on their anchorage/dock stops. CPU only, reads under 300 ms (rule 7).

**Decision:**
- **Labels:** a backfill (`uv run gfw-backfill`, 2023 →) of GFW port visits and 4Wings anchorage
  presence through the existing parsers; label rules (confidence ≥ 3, 2 h–60 d, not cut by the
  window) in `config/priors/c4.yaml`. Target is total dwell; the wait/berth split is not
  available from GFW and is left to the AIS state machine (DMA, later).
- **Features:** an observer at `as_of − lag` sees only events before it (C4-AC07, tested by
  truncation). Laid-up vessels stop counting after 60 days present, which is observable, instead
  of being dropped by their (future) final dwell. Lag 24 h by default (a CPA daily report);
  0 h and 96 h are reported as an ablation.
- **Models:** L0 median by type × flag × month; L1 three LightGBM quantile models conformalised
  by MAPIE (prefit CQR) with TreeSHAP drivers from LightGBM; L2 a random survival forest
  (scikit-survival) conditioned on time already in port, against Kaplan–Meier; L3 direct
  LightGBM per horizon with split-conformal bands, against seasonal naive.
- **Split:** train < validate < 45-day gap < test < 45-day gap < data end, so training and
  calibration labels are complete and the test is not biased short by GFW's publication rule.
- **Replay:** the test-window models make daily noon snapshots stored in `prediction`; the API
  only reads them, and the UI shows the actual outcome next to each prediction (REPLAY badge).

**Alternatives considered:** CoxPH gradient boosting (C-index 0.665 vs 0.651, but 20× slower to
fit); quantile LightGBM bands without conformalisation (43–50 % coverage on the queue); a deep
model (TFT, the multimodal transformer) before the baselines are beaten (rule 5);
predictions computed per request (≈ 1 s with the DB read, over budget).

**Consequences:** + real labels at scale, honest point-in-time evaluation, sub-30 ms reads.
− No live picture of Chattogram: the newest complete snapshot is ≈ 45 days old; vessel size and
draught are not yet features (GFW identity not fetched); Mongla has too few calls for its own
model; GFW's non-commercial licence applies to the trained models.
