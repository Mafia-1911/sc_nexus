# 08 · Nexus layer: what makes five models one platform

**TL;DR.** The Nexus layer (`packages/nexus`) turns separate predictions into decisions. It covers shipment tracking (door ETA built from vessel, port and inland legs), a scenario engine that runs one shock through every capability, evidence fusion (news plus physical signals giving a confidence score), a recommendation engine (actions with expected value), a daily brief and copilot (grounded, cited), a backtesting "time machine", and a carbon ledger. Most of the demo's "wow" lives here, so design its hooks in M1 and build it in M8, wiring each capability in as it lands.

## 1. Shipment tracker: "Where's my container, and when is it at my door?"

- **Inputs:** shipment, legs and DCSA-style `transport_event` rows (synthetic for shipments; real vessel positions from AIS), vessel ETA (AIS-reported plus a model-adjusted value), **C4** port-call predictions (wait and berth, P10/P50/P90), the derived **container dwell** estimate (yard and customs: a distribution calibrated to reported Chattogram averages, adjusted by C2 events such as customs outages), and **C3** inland route time distributions for the chosen option.
- **Method:** Monte Carlo convolution of the leg distributions (≥ 1,000 samples, seeded) gives door-ETA P10/P50/P90 and **on-time probability** against the order's due date.
- **Output:** `shipment.predicted_eta_p50/p90`, a timeline (planned, estimated and actual events) and the risk drivers ("+2.1 d anchorage wait, +1.4 d rail slot scarcity").
- **NX-R01:** recomputed on `port_call.updated`, `disruption.*` and `route` selection events.

## 2. Scenario engine

- **Scenario definition** (`config/scenarios/*.yaml`, or built in the UI):
  ```yaml
  id: cyclone-ctg-48h
  seed: 42
  start: 2026-11-03T00:00Z
  shocks:
    - type: PORT_OPERATIONS_SUSPENDED   # DisruptionType
      at: BDCGP
      duration_h: {p50: 36, p90: 60}
    - type: SUPPLIER_INCIDENT
      at: facility:fabric-mill-x        # fictional
      lead_time_delta_d: 5
  horizon_d: 21
  policies: [baseline, nexus_recommended]
  ```
- **Propagation order:** shocks become synthetic `disruption_event` rows (flagged `scenario_id`), then **C4** port state and dwell, then **C1** cascade and TTS/TTR, then the **inventory** buffer check, then the **C3** re-plan (alternative port, mode or departure), then the **C5** interplay (quarantined batches reduce available-to-promise), and finally KPIs.
- **Policies:** `baseline` (do nothing) vs `nexus_recommended` (accept the top recommendations automatically) vs `custom` (the user ticks actions).
- **Output:** a `scenario_result` per capability, plus a comparison table: orders late, revenue at risk, cost, CO2e, OTIF (K-05, K-06, K-07).
- **NX-R02:** deterministic for a fixed seed; the golden-path scenario reruns in < 30 s on CPU.

## 3. Evidence fusion (disruption confidence)

- **Signals:** C2 news clusters (count, source diversity, reliability), GDACS/ReliefWeb alerts, **physical anomalies** from C4 (anchorage queue z-score, departures dropping to zero, AIS-dark gaps, a SAR count jump), official notices (CPA, if available) and pharma regulatory feeds.
- **Method:** a log-odds combination per event: `logit(conf) = prior(type) + Σ wᵢ·sᵢ`, with weights hand-set in `config/priors/fusion.yaml` and tuned on backtests. Keep it explainable. Each contributing signal becomes a "corroborated by" chip with a link to the evidence.
- **NX-R03:** events from a single low-reliability source never exceed a confidence of 0.5 without physical corroboration.

## 4. Recommendation engine

- **Action catalogue** (`recommendation.action_type`): `increase_safety_stock`, `pull_forward_po`, `dual_source`, `reroute` (port or path), `mode_shift`, `shift_departure`, `expedite_air`, `reinspect`, `hold_shipment`, `notify_customer`.
- **Generation:** rules per event type and affected entity, scored by **expected value** = E[loss avoided] − cost, where the loss comes from C1/NX simulation and the cost from C3 cost models and holding-cost rates. Include confidence and a rationale built from evidence IDs.
- **Buffer maths** (the C2 deliverable, applied here): safety stock `SS = z·√(L̄·σ_d² + d̄²·σ_L²)`, with L̄ and σ_L inflated by the event's lead-time delta distribution. Output days of cover and units. Constraints: pharma shelf life and cold-storage capacity; garment season ship-by dates and MOQs.
- **Feedback:** Accept and Dismiss are stored with a reason. The weekly "useful rate" is K-04.
- **NX-R04:** every recommendation shows what, why, cost, benefit, confidence and evidence; nothing is auto-executed.

## 5. Daily brief and "Ask Nexus" (optional, Q-17)

- **Daily brief:** an LLM (per Q-03) summarises **structured rows** (top events, at-risk shipments, forecasts), never raw web text. Each sentence cites row IDs, which the UI renders as chips. If no LLM is available, use a deterministic template.
- **Ask Nexus (stretch):** read-only tool calling over the `/api/v1` endpoints (e.g. "Which Gazipur factories depend on Chattogram with TTS < 5 days?"). Optionally expose the same read-only tools as an **MCP server**, so external agents can query the platform.
- **NX-R05:** zero uncited numeric claims; refuse questions outside the platform's data.

## 6. Backtesting "time machine"

- Replays historical windows through the pipelines using only data available **as of** each moment (point-in-time features, GDELT and GDACS history, GFW port visits).
- **Candidate windows** (verify dates and coverage in M0): Cyclone Remal (late May 2024); the Red Sea diversions (from Dec 2023); Bangladesh's July–Aug 2024 unrest and internet shutdown (port and customs effects); the Chattogram–Kamalapur container-train shortage (May–Aug 2025); an Eid holiday window.
- **Measures:** K-03 alert lead time, K-04 precision, C4 forecast error during stress, and whether the recommendations would have helped (counterfactual run through the simulator).
- **UI:** the time-travel control in the top bar drives the whole app into backtest mode, shown with a clear banner.

## 7. Carbon ledger

- Per shipment leg: CO2e from **C3** emission models (ISO 14083 / GLEC method; factor source and year recorded), plus port-stay emissions if available (stretch).
- Exports a buyer-ready **Scope 3 transport report** (CSV/PDF) per order. Garment buyers increasingly ask for this.
- **NX-R06:** every CO2e number links to its factor table row.

## 8. Acceptance (G3)

| ID | Criterion |
|---|---|
| NX-AC01 | The golden-path scenario runs end to end in replay mode, without network, in < 30 s of compute, and the UI walk-through is < 7 min |
| NX-AC02 | The door-ETA P50/P90 and on-time probability are shown for every in-transit demo shipment and update after a disruption event |
| NX-AC03 | The cyclone event shows ≥ 2 corroborating signals of different kinds (news + physical or hazard feed) |
| NX-AC04 | ≥ 3 recommendation types appear in the golden path, each with expected value, confidence and evidence |
| NX-AC05 | The scenario comparison table shows baseline vs recommended policies across K-05, K-06 and K-07 |
| NX-AC06 | At least one backtest window reports K-03 and K-04 with honest numbers, including misses |
