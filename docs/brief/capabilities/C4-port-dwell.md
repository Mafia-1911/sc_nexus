# C4 · Port dwell prediction (vessel dwell: anchorage wait + berth time)

**TL;DR.** Predict, for each vessel calling at Chattogram (then Mongla and Payra): its **anchorage waiting time**, its **berth time** and its **total dwell**, as P10/P50/P90 with calibrated intervals (D-04). Also forecast **port-level congestion** (queue length, mean wait) 1–14 days ahead. Free full-resolution historical AIS for Chattogram isn't available, so the data plan combines: (1) **our own live aisstream collection from day 1**; (2) **GFW port-visit events** (all vessel types) as historical vessel-level labels; (3) **GFW hourly AIS presence** to rebuild queue history; (4) **IMF PortWatch** daily port calls; (5) clean Danish and US AIS to develop and pretrain the segmentation and models; (6) a calibrated SimPy DES to fill gaps. The ladder runs: median → **LightGBM quantile + conformal** → **survival model for remaining wait** → **time-series foundation models** for port-level forecasts → (stretch) a **multimodal port-state transformer** trained in a notebook. Satellite: use **GFW SAR detections** first, plus Sentinel-1/2 scenes for validation in the UI. Build order: 4 of 5.

## 1. Job to be done

- **C4-R01** As a garment logistics manager, I know when the vessel carrying my containers will berth and leave (P50 and P90), so I can plan trucks and production.
- **C4-R02** As a port/ICD analyst, I get a 7–14 day congestion forecast with drivers (arrival bunching, tides, weather and cyclone signals, holidays, strikes).
- **C4-R03** For vessels already waiting, the prediction updates as time passes (remaining wait, not the original estimate).
- **C4-R04** (Later) A derived **container-dwell** estimate (yard and customs) feeds the door-ETA and C3 port exit.

## 2. Hackathon scope

- **Must:** geofences; the port-call state machine; GFW port-visit ingest; a point-in-time feature store; baseline median → LightGBM quantile + conformal (MAPIE); the remaining-wait survival model; a port-level queue forecast (seasonal-naive baseline vs a TSFM); the Ports & Vessels UI; live updates from the collector.
- **Should:** queueing-theory features; tide windows; news-as-sensor features from C2; SAR counts (GFW) vs AIS counts as a data-quality signal; Mongla.
- **Stretch:** the multimodal port-state transformer (pretrain on DMA/NOAA + DES, fine-tune on Chattogram); our own Sentinel-1 ship detector; Payra; container-dwell model.

## 3. Inputs

| Need | Source | Notes |
|---|---|---|
| Live positions and static data (type, dimensions, draught, destination, ETA) | DS-AIS-01 | Persist on arrival. Measure coverage in M0 (Bay of Bengal terrestrial receivers may be sparse) |
| Historical vessel-level labels | DS-AIS-02 port visits (`public-global-port-visits-events`) | Check whether the visit window includes anchorage time. Examine the event structure and confidence levels in M0. NC licence |
| Historical queue reconstruction | DS-AIS-02 4Wings presence (hourly, all types) over anchorage polygons | ~96 h latency; aggregated |
| Port-level daily calls | DS-PORT-01 PortWatch | By vessel type; blackout days |
| Calibration | DS-PORT-02/03 (UNCTAD median time in port; CPPI), press-reported queue sizes (C2 news-as-sensor) | — |
| Geometry | DS-PORT-06 (OSM), DS-PORT-09 (GFW anchorages), DBSCAN/HDBSCAN on stationary AIS points | Port limits, anchorages, channel, berths/terminals |
| Exogenous data | DS-WX-01 (wind, rain, waves; **tide** via `sea_level_height_msl`), DS-WX-02 (cyclone alerts), DS-WX-04 (holidays incl. Eid), C2 events (strikes, customs outages), DS-NEWS-06 (GSCPI), PortWatch chokepoint transits (arrival bunching after Red Sea diversions) | Use only what is known as of prediction time |
| Satellite | DS-SAT-04 (GFW SAR presence), DS-SAT-01 (S1/S2 scenes) | Sparse (revisit ~6–12 days for S1; clouds for S2) |
| Pretraining/dev | DS-AIS-03 (DMA), DS-AIS-04 (NOAA) | Clean full-resolution tracks |
| Gap filling and stress | `sim/port_des.py` | Calibrated; labelled synthetic |

## 4. Port-call construction (the label factory)

1. **Clean AIS:** dedupe; drop invalid MMSIs; speed and teleport outliers; join static messages (ShipStaticData); treat `draught`, `destination` and `ETA` as noisy, human-entered fields.
2. **Zones:** port limit, outer anchorage polygons (OSM seamarks, GFW anchorages, clusters of SOG < 0.5 kn points), Karnaphuli channel, terminal and berth polygons (CCT, NCT, PCT, GCB, jetties; verify operators). Store them in `port_zone` with their source.
3. **State machine with hysteresis:** `APPROACH → ANCHORED` (inside an anchorage zone, SOG < 0.5 kn for ≥ 30 min, or nav_status = at anchor) `→ TRANSIT` (channel) `→ BERTHED` (inside a berth zone, SOG ≈ 0 or nav_status = moored, ≥ 30 min) `→ SHIFT` (berth to berth) `→ DEPARTED` (exits the port limit). Gaps of ≥ 6 h set `quality_flags.gap`, and multi-visit loops are split.
4. **Outputs:** `port_call` with segment timestamps, `waiting_h`, `berth_h`, `dwell_h`, `censored` for active calls, and `method` (`ais_state_machine`, `gfw`, `sim`).
5. **Cross-check:** compare our state-machine calls with GFW port visits over the overlap window, and report the agreement (C4-AC02).

## 5. Features (point-in-time correct, as of t)

- **Vessel:** type group, LOA, beam, draught (and draught vs channel limit, which forces a tidal window), DWT/GT if known, liner vs tramp (repeat-caller pattern), last port.
- **Queue state:** vessels ahead by type and size class; berth occupancy by class; arrivals and departures over the last 24/72 h; current mean elapsed wait; departures-per-day trend.
- **Queueing theory (physics-informed):** estimated arrival rate λ, service rate μ and servers c per berth class, giving **Erlang-C / Allen–Cunneen** approximations of the expected wait and utilisation ρ.
- **Tide and weather:** the next high-water windows (48 h) when draught requires them; wind, gusts, rain, waves (now plus forecast); cyclone signal level.
- **Calendar:** hour, weekday, Ramadan/Eid proximity, national holidays, fiscal year-end.
- **Events:** active C2 events within R km and their severity and type (strike, customs, port suspension).
- **Macro:** PortWatch 7-day call trend; chokepoint transit anomalies; GSCPI (monthly).
- **Satellite:** the latest SAR count in the anchorage polygons and its age in hours; the gap between SAR and AIS counts (dark vessels).

## 6. Method ladder

| Level | Target | Method |
|---|---|---|
| L0 | Wait, berth, dwell | Historical median by vessel type × size bin × month |
| L1 | Wait, berth, dwell at anchorage arrival | **LightGBM quantile regression** (P10/P50/P90) + **conformalised quantile regression** (MAPIE) for calibrated 80/90 % intervals; SHAP drivers |
| L2 | **Remaining** wait for active calls | **Survival** on elapsed time: XGBoost-AFT or scikit-survival RSF (DeepHit via pycox optional). Uses right-censored active calls; refreshes every 30–60 min |
| L3 | Port-level queue length and mean wait, 1–14 days | Seasonal-naive and LightGBM-direct baselines vs **TSFM zero-shot with covariates**: **Chronos-2** (covariate-aware; led GIFT-Eval at its Oct 2025 release over TimesFM-2.5 and TiRex). Also check newer leaderboard entries (e.g. TimesFM-3, Timestral; **verify claims on GIFT-Eval/fev-bench**). Optional TFT (PyTorch Forecasting/NeuralForecast) trained in a notebook. Pick the best on rolling-origin backtests |
| L4 (stretch) | Per-vessel quantiles or hazard | **Multimodal port-state transformer.** Tokens: [vessel static + approach-track encoding (TrAISformer-style discretisation, or an MLP over the resampled track)] ⊕ [**set** of vessels in queue/berths, through a permutation-invariant set-attention encoder] ⊕ [14-day port-state history] ⊕ [exogenous tokens: tide windows, weather forecast, holidays, C2 event embeddings] ⊕ [satellite token with observation-age embedding; **modality dropout** when missing]. A vessel query cross-attends to the context. Heads: quantiles (pinball loss) or a discrete-time hazard. Pretrain on DMA/NOAA calls + DES, fine-tune on Chattogram (GFW + live). Train on Kaggle T4; export to ONNX; < 50 ms per vessel on CPU. **Adopt only if it beats L1/L2 on the Chattogram holdout** (ADR), with ablations (−satellite, −news, −queue set) |
| Derived (later) | Container dwell | Discharge time (from berth segment) + yard/customs dwell distribution (calibrated to reported averages; shifted by C2 customs events) → used by NX door-ETA and C3 |

## 7. Evaluation and acceptance

**Splits:** time-based (train / validate / test by date); rolling-origin for port-level forecasts; no random splits. Report by vessel type and during stress windows (backtests).

| ID | Criterion |
|---|---|
| C4-AC01 | M0 measured aisstream coverage for the Chattogram bboxes (messages per hour, unique MMSIs per day) and the GFW port-visit history depth; numbers recorded in the source cards |
| C4-AC02 | State-machine calls agree with GFW port visits on ≥ 85 % of matched calls (start/end within 3 h), or the disagreement is explained |
| C4-AC03 | L1 beats L0 by ≥ 15 % in MAE on total dwell, or the card explains why not |
| C4-AC04 | 80 % prediction intervals cover 75–85 % on the test period (after conformalisation) |
| C4-AC05 | Survival model: C-index and integrated Brier score reported; remaining-wait predictions refresh within 15 min of new positions |
| C4-AC06 | Port-level forecast: MASE and WQL vs seasonal naive reported for the 7-day horizon; the chosen model beats naive |
| C4-AC07 | All features are point-in-time correct (a leakage test fails the build if a feature reads data after `as_of`) |
| C4-AC08 | The UI shows intervals and the top drivers for every prediction; SAR vs AIS counts are shown with the observation age |

## 8. API

`GET /ports/{locode}/state` (zones, queue, berths, vessels) · `GET /ports/{locode}/forecast?horizon_d=14` · `GET /ports/{locode}/calls?status=active|completed&since=` · `GET /vessels/{mmsi_or_imo}` · `GET /vessels/{id}/prediction` · `GET /ports/{locode}/satellite/latest`

## 9. UI

The Ports & Vessels page: a map (anchorage density via H3, vessel icons by state, zones), the queue timeline plus a 14-day fan chart, a vessel table (ETA, predicted wait/berth/departure with intervals, drivers), a vessel drawer (track replay, segment timeline, explanation), a satellite card (latest scene thumbnail, detections vs AIS count, age) and data badges throughout.

## 10. Integration hooks

NX shipment tracker (port legs; container dwell), C3 (port-exit time distributions; alternative ports), C2 (events as features; news-as-sensor; physical corroboration of events), C1 (lane lead times), and scenarios (closures change the DES and the features).

## 11. Risks and guardrails

- **Sparse AIS coverage:** measure it early; GFW presence and port visits as the backbone; replay for the demo.
- **Label noise:** drifting vs anchored, lighterage operations at Kutubdia. Use quality flags and exclusion rules.
- **Leakage:** point-in-time feature store, plus the test in C4-AC07.
- **Draught and ETA fields are self-reported.**
- **Licence:** GFW is non-commercial (flag it).
- **Satellite over-promising:** be explicit about revisit frequency and clouds.
- Open questions: Q-15.
