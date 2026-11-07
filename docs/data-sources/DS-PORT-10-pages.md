# DS-PORT-10 · what cpatos.gov.bd publishes, page by page (2026-11-08)

Companion to the generated card `DS-PORT-10.md`. Public pages only; no robots.txt, no terms found.

| Page | Content | Used for | Poll |
|---|---|---|---|
| `/pcs/` | every vessel visit: visit ref, rotation, phase (INBOUND, ARRIVED, WORKING, COMPLETE, DEPARTED), ETA, ATA, berth, operator, agent, ETD, ATD (226 visits) | port calls; Ships table; C4 labels | 15 min |
| `/tosdashboard/vesselAtBerth.php` | container vessels at berth: berth, berthed-on, ETD, occupation, import (total / discharged / balance, box and TEU), export (total / loaded / to ship, laden and empty) | real berthing times, cargo progress | 15 min |
| `vesselAtBerth_BreakBulk.php` | break-bulk vessels, most lightering at the outer anchorage; keeps months-old rows | anchorage population (recent rows) | 15 min |
| `yardOccupance.php` | per terminal yard: capacity, used, free TEU, %, boxes | congestion signal (map card; C4 / fusion next) | hourly |
| `day_wise_lying_container.php` | containers lying by location | container dwell evidence (door ETA next) | hourly |
| `last24_hour_position.php` | lying FCL / LCL / ICD / empty / export TEU; last-24 h handling | port state | 15 min |
| `24HoursperformanceReport.php` | per-vessel discharge / loading (actual vs CTMS) | port state (often empty) | 15 min |
| `berthOccupance.php` | monthly vessels and berth hours | context | daily |
| `sailed_vessel.php`, `all_gate_in_out_report.php`, `vesselReport.php` | date-range POST forms | not yet: sailed-vessel backfill (berth-time labels), gate in/out (truck flows, C3) | — |
| `mis_equipment_*`, `rtg_uses_report.php`, `yardWiseEquipPerformance.php`, `equipment_positon…` | crane and yard equipment | not used | — |
| PCS login areas, APKs, PDF manuals | user functions, guides | not used | — |
