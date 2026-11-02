# Golden path: the demo script (NX-AC01)

One connected story in about 6 minutes: a cyclone forms in the Bay of Bengal, Chattogram
suspends cargo handling, and a Gazipur garment exporter's orders are at risk. Everything runs
from replayed and synthetic data on this laptop; all firms are fictional.

## Before the audience arrives

```bash
make up              # if the stack is not running (first build: several minutes)
make golden          # offline worker (no live fetches, no LLM), fresh decisions, timed compute
make golden-walk     # optional rehearsal: the 8 steps in a browser with the network cut
```

`make golden` prints each compute step; the whole chain takes **≈ 4.5 s** (budget 30 s).
`make golden-walk` writes `docs/golden-path.json`: last run, all 8 steps in **5.2 s** of machine
time with every non-local request blocked. Run `make golden` again after a rehearsal: it clears
the decisions you accepted on stage.

Open http://127.0.0.1:3000 and pick **Cyclone shuts Chattogram + denim mill flood** (synthetic scenarios) in the data
selector (top right).

## The 8 steps (≈ 45 s each)

| # | Page | Click | Say (the numbers are what the system shows today) |
|---|---|---|---|
| 1 | Control Tower | — | "Fifty vessels wait off Chattogram. Every number carries its data mode. Each shipment has a door ETA with P(on time)." |
| 2 | Disruption Radar | "Chattogram port suspends cargo handling" | "News says the port is stopping. On its own that is 67 % confidence; the cyclone alert from the hazard feed corroborates it, so Nexus fuses it to **86 %**. Port departures show no drop yet: noted, not held against it." |
| 3 | Ports & Vessels | first vessel in the table | "The congestion forecast and each vessel's window, with the drivers behind the estimate." |
| 4 | Supplier Network | the Chattogram row | "Chattogram tops the risk leaderboard: the network's single point of failure, with its time to survive shorter than its time to recover." |
| 5 | Disruption Radar → **Feeds** → "Tropical Cyclone SYN-01" | **Accept** on "Export via BDMGL" | "The goods are already made; the shut port is what makes them late, so stock would not help. Nexus proposes exporting via Mongla: expected value **≈ US$89K** at 95 % confidence, with its evidence. Nothing runs until a person accepts." |
| 6 | Route Planner | **Plan route** | "After discharge, the Pareto options: fastest, cheapest, lowest CO2e, each with P(on time)." |
| 7 | Quality Lab | Status → rejected, first lot | "A lot failed AQL: the heatmaps show where; the options are costed against the order it puts at risk." |
| 8 | Scenario Studio | **Export one page (PDF)** | "Same shock, with and without Nexus: **2.2 orders saved**, OTIF **+1.6 points**, **US$98K net** after the cost of the actions." |

Close (30 s): the backtest on real 2023–2026 data, in `docs/model-cards/nexus-backtest.md`:
the hazard alerts came **34–53 h before** Chattogram's worst day when a storm hit, and 4 of 7
alerts were false alarms. Honest numbers, misses included.

## Known gaps (say them if asked)

- **The basemap needs the internet.** Map tiles come from OpenFreeMap (the only host the offline
  walk blocked); vessels, events and routes still draw without it. A local basemap is on the
  polish list.
- **In-transit orders look late in both columns** of the studio: synthetic due dates fall ≈ 5 h
  after the planned delivery (a data artefact, in the door-ETA model card).
- Rates, costs and reroute capacity are estimates, labelled in the UI and the model cards.
- Backup if anything fails: the screenshots in `docs/screenshots/` (light and dark per page).
