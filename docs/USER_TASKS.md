# Tasks for the user

Lower-value or manual work the agent hands over so it can keep coding. Tick a box when done and
tell the agent; each item says where its result goes.

## Open

- [ ] **OSM extract (C3):** download https://download.geofabrik.de/asia/bangladesh-latest.osm.pbf
      (≈ 340 MB) to `data/raw/DS-GEO-01/bangladesh-latest.osm.pbf`. Then the agent runs
      `uv run c3 build-graph`.
- [ ] **Ollama for Docker:** `sudo systemctl daemon-reload && sudo systemctl restart ollama`, then
      `ss -ltn | grep 11434` should show `0.0.0.0:11434` (now it shows `127.0.0.1`). Until then the
      worker's hourly `c2:llm` job skips.
- [ ] **Truck ban in Dhaka (C3-AC06):** check the current Dhaka Metropolitan Police rule for
      heavy vehicles (hours, zone, exemptions for garments and medicines). Edit `road.truck_ban`
      in `config/priors/c3.yaml` (now 07:00–22:00 within 8 km of the centre, an estimate).
- [ ] **Rail and barge tariffs and timetables (C3):** confirm with Bangladesh Railway / CPA /
      Medlog: Chattogram→Kamalapur tariff per 20 ft (now Tk 28,000), loaded trains per day (now
      2 slots, 35 % cancelled), Pangaon barge fare (now US$190 per laden 20 ft) and sailing days
      (now Mon and Thu). Edit `services:` in `config/priors/c3.yaml` with the source and date.
- [ ] **BDT/USD rate:** the `fx_rate` table is empty; give a rate with its source and date (now
      122, an estimate) or point to a free FX source to ingest.
- [ ] **More DMA AIS days (C4, M6):** six more days (e.g. `aisdk-2025-02-21` … `-26`) into
      `data/inbox/DS-AIS-03/`.

## Done

- [x] C2 gold labels (150 articles) → `data/samples/c2_gold/gold.csv`.
- [x] `qwen3:4b` pulled; Q-10 English only; Q-12 analytics now, GNN later; C3 next.
