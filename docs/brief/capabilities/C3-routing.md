# C3 · Routing optimisation (multimodal, multi-objective)

**TL;DR.** Given an origin (port, terminal, ICD), a destination (warehouse, factory, DC), a cargo profile and a deadline, return a **Pareto set** of plans trading off **time (P50/P90)**, **cost (BDT/USD)** and **CO2e (ISO 14083 / GLEC method)**. Each plan comes with an **on-time probability** and a best **departure window**. The network is a Bangladesh corridor graph built from OSM roads plus scheduled **rail** (Chattogram ↔ Kamalapur ICD) and **barge** (Chattogram ↔ Pangaon) services, with transfer nodes. Exact and heuristic optimisers are the baseline. **RL is an experiment** that must beat them on dynamic re-routing before it is adopted. Traffic is *modelled* (time-of-day profiles), never claimed as live. Build order: 3 of 5.

## 1. Job to be done

- **C3-R01** As a garment logistics manager, I have containers discharging at Chattogram that must reach my Gazipur warehouse by Thursday 18:00. I want the fastest, cheapest and greenest options, plus the trade-off between them, with their reliability.
- **C3-R02** As a pharma distributor, I need a **cold-chain-safe** plan (maximum transit hours, reefer-capable legs) with an on-time probability.
- **C3-R03** When a disruption hits (a C2 event or a C4 congestion spike), I want re-route or mode-shift suggestions automatically.
- **C3-R04** I want the departure time that avoids congestion and any truck restrictions.

## 2. Hackathon scope

- **Must:** a corridor road graph (Chattogram, Dhaka, Gazipur, Savar, Narayanganj) from the Geofabrik extract; time, cost and CO2e models; a Pareto planner for road-only; time-dependent travel time; on-time probability; the Route Planner UI.
- **Should:** multimodal composition with rail and barge services and transfers; departure-window optimisation; the Mongla/Payra alternative-port story (Q-13); constraints from C2 events; port-exit time from C4 and container dwell.
- **Stretch:** multi-drop fleet VRP-TW (PyVRP); an RL dynamic re-routing experiment (MORL or RL4CO); sea legs and transshipment (searoute + C4 dwell at Colombo/Singapore).

## 3. Inputs

DS-GEO-01/02 (OSM), DS-GEO-03 (ORS, for calibration and validation only), DS-GEO-05 (emission factors), DS-GEO-06 (fuel, tolls, tariffs: a manual table with sources), DS-PORT-05/06 (ports, ICDs), DS-WX-01 (weather adjustments, stretch), the rail and barge service generator (`sim`, calibrated to 2025 press facts), C4 (port, ICD and container-dwell distributions), and C2 (closures and restrictions).

## 4. Network model

- **Road:** OSMnx/pyrosm drivable graph, filtered to truck-relevant classes (motorway, trunk, primary, secondary, tertiary and links), simplified and consolidated. Edge attributes: length, class, lanes, maxspeed (with defaults per class where missing), bridge, toll (from the table), restricted windows (truck bans: **verify the current DMP rules and Eid notices**; model them as time-windowed edge closures with cargo exemptions, since recent Eid notices exempted garments and medicines).
- **Rail:** OSM railway plus **service edges** (departure times, capacity in TEU, transit time, tariff). Train availability varies (2025: 125 trains in May, 91 in June, 83 in July and 68 in August up to the 24th, against a stated need of 6–7 a day) and is modelled as a stochastic slot supply.
- **Barge:** inland waterway service edges between Chattogram and Pangaon (few vessels; frequency and capacity limited; slow, low CO2e).
- **Transfer nodes:** port gate, off-dock ICDs and depots, Kamalapur ICD, Pangaon ICT, rail yards. Each has a handling-time distribution, a cost, and opening hours.
- **Time-expanded layer:** scheduled services are expanded over the planning horizon; road edges carry hour-of-week speed multipliers per class (synthetic profiles, calibrated against ORS durations for sample O/D pairs and any published studies; labelled *modelled*).

## 5. Objectives and constraints

- **Time:** a per-segment lognormal travel time (median from the time-dependent speed; dispersion by class and hour) plus waits for services and transfer dwell. Monte Carlo over the path gives P50, P90 and the **on-time probability** against the deadline.
- **Cost:** truck (fuel L/km × diesel price + driver hours + tolls + trip fees), rail and barge tariffs, handling, plus a **late penalty** (demurrage, detention or a buyer penalty from the order).
- **CO2e:** `Σ tonnes × km × factor(mode, vehicle, load factor)` using the WTW factors (GLEC/DESNZ; source and year stored). Road gets a congestion adjustment (a COPERT-style speed curve) and reefer gets an uplift. Report per shipment and per TEU (K-07).
- **Constraints:** deadline and time windows, capacity, cold chain (maximum transit hours; reefer power at transfers), dangerous-goods restrictions, bans and closures (C2), service capacity.

## 6. Method ladder

| Level | Method | Notes |
|---|---|---|
| L0 | Single-objective Dijkstra/A* for time, cost and CO2e separately; a weighted sum from user sliders | Baseline and sanity check |
| L1 | **Pareto planner:** multi-objective label-setting (Martins-style / NAMOA*) on the corridor graph (small enough), *or* Yen k-shortest paths × weight sweeps followed by a non-dominated filter. Time-dependence comes from sampling departures every 30–60 min | Return 3–7 diverse non-dominated plans |
| L2 | **Multimodal composition:** road-only vs road+rail vs road+barge mode chains over the time-expanded services, with transfer costs and times; the Pareto set across chains | Mode-shift recommendations |
| L2 | **Departure-window optimisation:** a 24–48 h sweep giving a heat strip of P90 arrival and cost; respects bans | "Leave at 22:00: −3 h, −8 % CO2e" (illustrative) |
| L3 | **Fleet VRP-TW** (stretch): **PyVRP** (hybrid genetic search) or OR-Tools for multi-drop deliveries from an ICD to several factories with time windows and capacities; weight sweeps for multi-objective | Sanity-check on Solomon instances |
| L4 | **RL experiment** (stretch, Q-14): dynamic re-routing under stochastic disruptions in a simulator built on the same graph and C2 scenarios. MORL (MORL-Baselines: e.g. Envelope Q-learning or Pareto Conditioned Networks, preference-conditioned) and/or **RL4CO** neural solvers (POMO / attention model for CVRP-TW). **Benchmark against re-optimisation with L1–L3 on ≥ 50 held-out scenarios**; adopt only on lower regret | Train in a notebook; export the policy to ONNX; mark "experimental" in the UI |
| Option | **Valhalla** (truck costing, time-dependent) as a container, behind ADR-007, only if the OSMnx graph's realism gap is measured to matter | Avoids extra infrastructure by default |

## 7. Evaluation and acceptance

| ID | Criterion |
|---|---|
| C3-AC01 | On 20 calibration O/D pairs, the median absolute % error of travel time vs ORS (HGV) is ≤ 15 % after calibration; distances within 5 % |
| C3-AC02 | A typical Chattogram → Gazipur request returns ≥ 3 non-dominated plans (when they exist) in < 5 s on CPU |
| C3-AC03 | Every CO2e figure is traceable to a factor row (source and year); unit tests reproduce example calculations |
| C3-AC04 | The on-time probability is calibrated on synthetic ground truth: reliability-diagram error ≤ 0.1 |
| C3-AC05 | A C2 closure or C4 congestion scenario changes the recommended plan in a sensible way (scenario tests) |
| C3-AC06 | Bans and closures are respected (no plan uses a closed edge in a closed window), with exemptions applied by cargo |
| C3-AC07 | If VRP or RL is attempted: report the gap or regret vs baseline with confidence intervals; RL is adopted only per the ADR |

## 8. API

`POST /routes/optimize` (origin, destination, cargo_profile, qty_teu, deadline, constraints, weights, departure_window, which returns route options) · `GET /routes/{request_id}` · `GET /routes/{request_id}/departure-windows` · `POST /routes/vrp` (stretch) · `GET /network/services?mode=rail|barge`

## 9. UI

The Route Planner page: O/D pickers (ports, ICDs, warehouses; map click), cargo profile and deadline, three preference sliders, the **Pareto chart** (time vs cost, colour = CO2e band, using the depth ramp), plan cards (P50/P90, cost, CO2e, mode-mix bar, on-time probability gauge with label), map alternatives with mode-coloured legs, and the departure-window strip. Each plan has a *Why this plan?* explanation listing the binding constraints and the dominant cost and time terms.

## 10. Integration hooks

C4 (port-exit and ICD dwell distributions; congestion), C2 (closures, bans, strikes as time-windowed constraints), C1 (alternative lanes for mitigation), C5 (expedite after a quality failure), NX (shipment tracker inland leg; carbon ledger; scenarios).

## 11. Risks and guardrails

- **No live traffic:** label it as modelled and keep calibration evidence.
- **OSM topology errors in Bangladesh:** run connectivity checks and patch with a manual edge list (documented).
- **Rail and barge schedules are synthetic:** calibrate to the cited 2025 facts and label them.
- **Truck-ban rules:** verify them; make them configurable.
- **RL hype:** benchmark it honestly.
- Open questions: Q-13, Q-14.
