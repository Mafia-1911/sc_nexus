# Tasks for the user

Lower-value or manual work the agent hands over so it can keep coding. Tick a box when done and
tell the agent; each item says where its result goes.

## Open

- [ ] **Offline basemap (demo polish, venue Wi-Fi):** the maps load tiles from
      `tiles.openfreemap.org`, the golden path's one network dependency. Download once:
      1. The `pmtiles` tool (single binary) from https://github.com/protomaps/go-pmtiles/releases
         (`go-pmtiles_*_Linux_x86_64.tar.gz`), unpack it anywhere on your PATH.
      2. Pick the newest build date at https://maps.protomaps.com/builds/ (e.g. `20261116`), then
         from the repo root: `pmtiles extract https://build.protomaps.com/<DATE>.pmtiles
         apps/web/public/map/bangladesh.pmtiles --bbox=88.0,20.5,92.8,26.7 --maxzoom=14`
         (Bangladesh only, roughly 100–200 MB, never committed).
      3. Fonts and icons: download https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.zip
         and copy its `fonts/` folder to `apps/web/public/map/fonts/` and `sprites/v4/` to
         `apps/web/public/map/sprites/v4/`.
      Then `NEXT_PUBLIC_MAP_SOURCE=local` (in `.env`) makes every map use the local file; the
      deployed site keeps the online tiles.

- [ ] **Render (deployment: the API; no card):** sign up at https://render.com with GitHub, then
      New → Blueprint → pick the repo `sc_nexus`, branch `m3-c1` (it reads `render.yaml`). When it
      asks for the secret values, paste from `.env`: `DATABASE_URL` ← the value of
      `DATABASE_URL_UNPOOLED`, `API_TOKEN` ← `API_TOKEN`, `MAPBOX_API`, `DATADOCKED_APIKEY`. After the
      first deploy, put the service URL in `.env` as `RENDER_API_URL=https://….onrender.com`. The
      agent then deploys the website (`scripts/deploy_vercel.sh`) and starts the worker against Neon
      (`make worker-cloud`).

- [x] **Neon (deployment database, free tier; via Vercel's integration, names `DATABASE_URL` and `DATABASE_URL_UNPOOLED`):** sign up at https://neon.tech, create a project
      (region: AWS Asia Pacific, Singapore, closest to Bangladesh; Postgres 16 or newer), then copy
      two connection strings from "Connect" into `.env`: the **direct** one as
      `NEON_DATABASE_URL=...` (migrations and the initial copy) and the **pooled** one as
      `NEON_POOLED_URL=...` (the app and logins). The agent runs `scripts/deploy_db.sh` (enables
      PostGIS and pgvector, copies the current data: 368 MB; the free tier holds 0.5 GB).

- [x] **Vercel (the website):** sign up at https://vercel.com (Hobby, free), create a token at
      https://vercel.com/account/tokens and put it in `.env` as `VERCEL_TOKEN=...`. The agent
      runs `scripts/deploy_vercel.sh` (sets the environment variables, deploys `apps/web`).

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

- [x] **MVTec AD carpet and leather (C5-AC01):** from
      https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads take **Carpet**
      (`carpet.tar.xz`, 705 MB) and **Leather** (`leather.tar.xz`, 500 MB). Extract both into
      `data/raw/DS-VIS-01/mvtec/`:
      `tar -xJf carpet.tar.xz -C data/raw/DS-VIS-01/mvtec/` (same for leather). You should get
      `data/raw/DS-VIS-01/mvtec/carpet/train/good/000.png` etc. A partial `carpet/` folder is
      already there; extracting over it is fine. Licence CC BY-NC-SA 4.0 (non-commercial).
- [x] **CLIP weights for AnomalyCLIP (C5-AC01):** download ViT-L/14@336px (934 MB, MIT) from
      https://openaipublic.azureedge.net/clip/models/3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02/ViT-L-14-336px.pt
      to `data/cache/aclip/clip/ViT-L-14-336px.pt`. A partial 172 MB file from the agent's interrupted download is there; overwrite it. Check: `sha256sum` starts with `3035c92b`.
- [ x] **Run the AnomalyCLIP baseline (C5-AC01):** the repo clone, CPU venv and split manifest are
      ready in `data/cache/aclip/` (setup: `packages/c5_defect_intel/baselines/README.md`). From
      the repo root (≈ 1–2 h on CPU; results are saved per category):
      `A=data/cache/aclip; $A/venv/bin/python -I packages/c5_defect_intel/baselines/anomalyclip_eval.py --repo $PWD/$A/repo --manifest $A/manifest.json --clip-cache $PWD/$A/clip --out docs/model-cards/c5-eval-anomalyclip.json --categories pill capsule stitch carpet leather --threads 4`
      Result: `docs/model-cards/c5-eval-anomalyclip.json`; tell the agent and it adds the rows to
      the model card.
- [ ] **VisA (optional, C5-AC01's VisA capsules):** one archive,
      https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar (1.9 GB,
      CC BY 4.0). Extract into `data/raw/DS-VIS-02/`: `tar -xf VisA_20220922.tar -C
      data/raw/DS-VIS-02/` (only the `capsules/` folder is needed; the rest can be deleted).

- [ ] **Repair the NTFS drive (sudo)** (2026-11-17: still unreadable after the first repair, "Invalid argument"; `ntfsfix` fixes only a few NTFS errors, so run `chkdsk /f` on the drive from Windows): after the unclean reboot, three files show as `?????????`
      and can't be read or deleted: `docs/screenshots/quality-lab-dark.png`, `quality-lab-light.png`,
      `quality-lot-drawer.png`. Stop the stack (`make down`), close editors on the drive, then
      `sudo umount /run/media/mushh/NUSHAN && sudo ntfsfix -d /dev/sdc1` (or `chkdsk /f` on Windows,
      which repairs more). Re-mount; the agent then regenerates the Quality Lab screenshots. Until
      then `docs/screenshots` is kept out of Docker builds (A-094). Worth a backup of the drive first.

- [x] **TomTom Traffic key (C3 Route Planner live traffic):** sign up at
      https://developer.tomtom.com (free tier, no card), create an API key, put it in `.env` as
      `TOMTOM_API_KEY=…`. The agent then probes Dhaka–Chattogram coverage (traffic flow tiles and
      routing with live traffic) before wiring it into the map.
- [x] **DataDocked trial key (ship P&I insurance):** https://datadocked.com → "Get free API key"
      (20 free credits, no card; paid from ≈ €80/month after that, so treat it as a trial). Put
      it in `.env` as `DATADOCKED_API_KEY=…`. The agent caches each ship's answer (P&I cover renews
      yearly, around 20 Feb), so the credits cover the demo vessels only. Equasis
      (equasis.org, free account) shows the same field by hand if a ship is missing.

## Done

- [x] DMA AIS days 2025-02-27 … 2025-03-05 in `data/inbox/DS-AIS-03/` (03-01 re-fetched, complete).
- [x] Chattogram and Mongla channel limits in `config/priors/c4.yaml` (CPA circular 2023-03-19, MPA).
- Taken over by the agent (U-03): C4 press-reported queues, Q-15 (default), the TSFM run.
- [x] C2 gold labels (150 articles) → `data/samples/c2_gold/gold.csv`.
- [x] `qwen3:4b` pulled; Q-10 English only; Q-12 analytics now, GNN later; C3 next.
