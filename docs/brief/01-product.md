# 01 · Product: vision, context, users, demo, KPIs

**TL;DR.** Supply Chain Nexus is a control tower for Bangladeshi garment and pharma shippers. It predicts port delay, detects disruptions in the news, maps supplier dependencies, plans multimodal inland routes and links factory quality to delivery risk. Every recommendation shows its evidence, its uncertainty and its trade-offs in cost, time and CO2e. The hackathon demo is one connected story, the *golden path* (§5), and every feature should serve it.

## 1. Problem

Bangladesh's export economy runs through one congested gateway. Garments are the largest export, and the pharma industry relies on imported active pharmaceutical ingredients (APIs).

Context from desk research. Verify anything before it appears in the demo.

- Chattogram port handled about **3.41 M TEU in 2025** (Lloyd's List ranking, as reported by Dhaka Tribune). It is a tidal river port, so vessels queue at the outer anchorage. Press reports from congestion episodes describe waits of **2–8 days**.
- Rail carries only about **10 %** of Dhaka-bound containers (The Daily Star). In 2025, container trains on Chattogram–Kamalapur ran 125 in May, 91 in June, 83 in July and 68 in August up to the 24th, against a stated need of 6–7 trains a day.
- Import container dwell at Chattogram was about **8.3 days** in 2024, per press reports citing the World Bank LPI. Container dwell is not the C4 target (D-04), but it drives inland plans.
- Each Eid, the authorities ban trucks, covered vans and lorries from highways for several days. Recent notices exempted garments and medicines among other goods. Holidays matter.
- Shocks layer on top: Bay of Bengal cyclones (peaks Apr–May and Oct–Nov), monsoon flooding, strikes and blockades, customs system outages, rail wagon shortages and Red Sea rerouting.

**The gap:** shippers learn about delays late, from phone calls and news. They have no forward view of port congestion, no map of tier-2 and tier-3 dependencies, and no quick way to compare road, rail and river options. Quality failures surface after shipment plans are already locked.

## 2. Value proposition

1. **See earlier:** news and physical signals (AIS, satellite, hazard alerts) are fused into scored disruption events, hours or days before they hit operations.
2. **Know the exposure:** a supplier-port-product graph shows which orders are exposed and how long the network survives the shock compared with how long recovery takes (time-to-survive vs time-to-recover, TTS vs TTR).
3. **Act with trade-offs:** buffer, reroute, mode-shift or expedite recommendations, each with expected value, on-time probability and CO2e.
4. **Close the loop with quality:** a defective batch becomes delivery risk automatically, together with a fix plan.

## 3. Personas

| ID | Persona | Top jobs | Pages |
|---|---|---|---|
| P1 | **Import/logistics manager**, garment exporter (Gazipur or Ashulia) | When will my fabric containers be out of port? Which inland option should I book? How much buffer do I need? | Control Tower, Ports, Route Planner, Disruption Radar |
| P2 | **Supply planner**, pharma manufacturer (Savar or Gazipur) | How exposed are we to API suppliers in China and India? Can we keep the cold chain? What is the shelf-life risk? | Supplier Network, Disruption Radar, Route Planner |
| P3 | **Port/ICD operations analyst** | What will the queue and waiting time be over the next 7–14 days, and what is driving them? | Ports & Vessels |
| P4 | **QA manager**, plant | Inspection triage, AQL lot decisions, drift alarms, which orders are hit | Quality Lab |
| P5 | **Executive or hackathon judge** | What is at risk this week, what would you do, and what does it save? | Control Tower, Scenario Studio |

## 4. Industry packs (configuration, not forks)

Each pack is data plus config: product templates, BOMs, constraints, priors and copy. The code paths are shared.

**Garments (RMG)**

- **Flows:** cotton, yarn, fabric and trims are imported (largely from China and India: HS 52xx, 54xx, 55xx, 60xx, 9606, 9607). Cut-make-trim happens in Bangladesh, and finished garments (HS 61, 62) go out through Chattogram, transshipping at Colombo, Singapore or Port Klang to EU and US ports.
- **Constraints:** season ship-by dates, FOB deadlines, buyer compliance, an air-freight fallback that costs 5–10× sea freight (verify), and AQL inspection (commonly AQL 2.5 for major defects).
- **Defects:** fabric (stains, holes, slubs, oil, cuts), stitching (skipped, broken or overlapped stitches), shade variation, misprints.
- **Buyers want Scope 3 transport emissions.** Report CO2e per shipment following ISO 14083 and the GLEC framework.

**Pharma**

- **Flows:** APIs and excipients are imported (largely from China and India: HS 29xx and 3003/3004 inputs), along with packaging (aluminium foil, PVC). Finished dosage forms are made in Bangladesh plants for domestic distribution and export.
- **Constraints:** a cold chain at 2–8 °C for biologics, insulin and vaccines; Good Distribution Practice (GDP); shelf life and first-expiry-first-out (FEFO); regulators (DGDA, US FDA, EMA, WHO PQ); and batch release, which **always requires human QA sign-off**.
- **Defects:** tablets (chips, cracks, broken tablets, discolouration), capsules (dents, cracks, imprint faults), blisters (bad seal, missing tablet).
- **External risk signals:** FDA recalls, import alerts, warning letters and drug shortages.

## 5. The golden-path demo (≈ 6 minutes, one connected story)

Use fictional companies throughout, at real infrastructure (ports, ICDs, EPZs). The numbers below are illustrative; the demo must show real outputs from the system.

1. **Control Tower.** The live (or replayed) AIS map shows the Chattogram outer anchorage. KPI strip: vessels waiting, P50 forecast wait, active disruptions, orders at risk, and this week's CO2e.
2. **Disruption Radar.** A GDACS cyclone alert and a cluster of news articles become one event: "Cyclone signal; Chattogram operations suspended, est. 36–48 h". Confidence is high, *corroborated by* AIS (vessels leaving the anchorage) and the hazard feed. The affected port, lanes and suppliers are linked.
3. **Ports & Vessels.** The congestion fan chart shifts up. The vessel carrying Factory A's fabric moves from a Wednesday P50 berth to Saturday (P90 Monday), and the drivers are shown.
4. **Supplier Network.** Factory A's dependency on Fabric Mill X runs entirely through Chattogram, which makes the port a dominator, a single point of failure. A what-if (port closed 3 days, Mill X lead time +5 days) gives TTS 4 d < TTR 9 d, so 6 orders go late and revenue is at risk.
5. **Recommendation.** Raise the fabric safety stock at the Gazipur DC by N days of cover and pull the PO forward. The expected value and confidence are shown, with accept and dismiss buttons.
6. **Route Planner.** After discharge, three Pareto options appear: road direct (fastest), rail via the Kamalapur ICD (cheaper, lower CO2e, but a wide P90 because of the train shortage) and barge via Pangaon (cheapest and greenest, slowest). Each shows its on-time probability for the order deadline and the best departure window.
7. **Quality Lab.** Batch B-0412 at Factory A shows stain anomalies (heatmaps) and fails AQL. Units are quarantined, so an EU order is now at risk from both the delay and the defect. The options are rework plus an expedited air shipment, or renegotiation. The supplier's quality score feeds back into C1.
8. **Scenario Studio.** "With Nexus vs without": days late avoided, cost difference and CO2e difference, exportable as a one-page summary.

The pharma variant runs the same way: an Indian API supplier is hit by an FDA import alert (C2 via openFDA and FDA pages), C1 runs a what-if on antibiotic SKUs, buffers are recommended, and a cold-chain insulin route from Chattogram to a Savar DC is planned with an on-time probability.

## 6. KPIs (definitions live in code, `packages/core/kpis.py`)

| ID | KPI | Definition |
|---|---|---|
| K-01 | Vessel dwell forecast error | MAE (hours) of P50 total dwell at anchorage arrival, plus 80 % interval coverage |
| K-02 | Congestion forecast skill | MASE of the 7-day queue-length forecast vs seasonal naive |
| K-03 | Alert lead time | Hours between the first Nexus alert and the disruption's peak visibility in port data or the press (backtests) |
| K-04 | Alert precision | Share of alerts the user marks useful, or that match labelled events |
| K-05 | Orders at risk | Count and value of open orders whose P90 delivery is later than the due date |
| K-06 | OTIF uplift (scenario) | On-time-in-full with vs without the recommended actions |
| K-07 | CO2e per TEU | Per inland move, ISO 14083-style, with the route/mode breakdown |
| K-08 | Inspection quality | Image AUROC and recall at fixed FPR per category; time to triage |
| K-09 | Data freshness | Age of the latest record per source, against its expected cadence |

## 7. Non-goals (hackathon)

Multi-tenant SaaS, billing, mobile apps, customs automation, real ERP integration, automated GMP batch release, financial-credit scoring of real companies, live truck telematics, and anything that needs paid data.
