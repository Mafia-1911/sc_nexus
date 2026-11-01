# Tasks for the user

Lower-value or manual work the agent hands over so it can keep coding. Tick a box when done and
tell the agent; each item says where its result goes.

## Open

- [x] **OSM extract (C3):** download https://download.geofabrik.de/asia/bangladesh-latest.osm.pbf
      (≈ 340 MB) to `data/raw/DS-GEO-01/bangladesh-latest.osm.pbf`. Then the agent runs
      `uv run c3 build-graph`.
- [x] **Ollama for Docker:** `sudo systemctl daemon-reload && sudo systemctl restart ollama`, then
      `ss -ltn | grep 11434` should show `0.0.0.0:11434` (now it shows `127.0.0.1`). Until then the
      worker's hourly `c2:llm` job skips.
- [x] **Truck ban in Dhaka (C3-AC06):** check the current Dhaka Metropolitan Police rule for
      heavy vehicles (hours, zone, exemptions for garments and medicines). Edit `road.truck_ban`
      in `config/priors/c3.yaml` (now 07:00–22:00 within 8 km of the centre, an estimate).
- [ ] **Rail and barge tariffs and timetables (C3):** confirm with Bangladesh Railway / CPA /
      Medlog: Chattogram→Kamalapur tariff per 20 ft (now Tk 28,000), loaded trains per day (now
      2 slots, 35 % cancelled), Pangaon barge fare (now US$190 per laden 20 ft) and sailing days
      (now Mon and Thu). Edit `services:` in `config/priors/c3.yaml` with the source and date.
- [ ] **BDT/USD rate:** the `fx_rate` table is empty; give a rate with its source and date (now 122, an estimate) or point to a free FX source to ingest.
- [ ] **Truck travel time Chattogram→Dhaka (C3):** find one dated source (press, BRTA, a
      haulier) for a laden container truck's typical drive time on the N1 at night or off-peak.
      The model now says ≈ 6.2 h for Chattogram→Gazipur free flow; ORS says 3.7 h. Put the number
      and link in `config/priors/c3.yaml` next to `calibration`, and the agent rescales.

- [ ] **MVTec AD carpet and leather (C5-AC01):** from
      https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads take **Carpet**
      (`carpet.tar.xz`, 705 MB) and **Leather** (`leather.tar.xz`, 500 MB). Extract both into
      `data/raw/DS-VIS-01/mvtec/`:
      `tar -xJf carpet.tar.xz -C data/raw/DS-VIS-01/mvtec/` (same for leather). You should get
      `data/raw/DS-VIS-01/mvtec/carpet/train/good/000.png` etc. A partial `carpet/` folder is
      already there; extracting over it is fine. Licence CC BY-NC-SA 4.0 (non-commercial).
- [ ] **VisA (optional, C5-AC01's VisA capsules):** one archive,
      https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar (1.9 GB,
      CC BY 4.0). Extract into `data/raw/DS-VIS-02/`: `tar -xf VisA_20220922.tar -C
      data/raw/DS-VIS-02/` (only the `capsules/` folder is needed; the rest can be deleted).

## Done

- [x] DMA AIS days 2025-02-27 … 2025-03-05 in `data/inbox/DS-AIS-03/` (03-01 re-fetched, complete).
- [x] Chattogram and Mongla channel limits in `config/priors/c4.yaml` (CPA circular 2023-03-19, MPA).
- Taken over by the agent (U-03): C4 press-reported queues, Q-15 (default), the TSFM run.
- [x] C2 gold labels (150 articles) → `data/samples/c2_gold/gold.csv`.
- [x] `qwen3:4b` pulled; Q-10 English only; Q-12 analytics now, GNN later; C3 next.
