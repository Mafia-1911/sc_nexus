# 03 · Data sources, probing and synthetic data

**TL;DR.** Probe every free source before designing schemas (D-08). For each source: save the raw responses, write down the schema, auth, limits, licence and failure modes, and measure its Bangladesh coverage. Then build the backbone on synthetic data that uses the **same canonical schema**, and switch each source to `replay` or `live` as it gets verified. Paid sources are excluded (§2.10). Facts below come from desk research on 2026-10-26; anything marked *verify* is unconfirmed until M0 has probed it.

**Priority tiers.** **P0** = needed for the golden path; probe in M0. **P1** = valuable; probe in M0 if time allows. **P2** = later or stretch. **X** = excluded (paid).

## 1. How the agent records a source (source card)

Create `docs/data-sources/<DS-ID>.md` from this template, and mirror the key fields into `config/sources.yaml`:

```markdown
# DS-XXX-nn · <name>
status: verified | needs-registration | blocked | paid-excluded | deprecated
tier: P0|P1|P2   used_by: [C4, NX]   default_mode: live|replay|synthetic
auth: none | api-key (ENV_VAR) | oauth | account-download   signup: <url>
protocol: REST | WebSocket | file-download | ArcGIS FeatureServer | STAC | RSS
endpoints probed: <method url params>   pagination: <how>
limits (documented): …   limits (observed): headers, 429 behaviour
licence/terms: …   attribution text: …   NC? yes/no
freshness/latency: …   history depth: …   update cadence: …
Bangladesh coverage: <measured counts in bbox/time window>
schema: link to schemas/raw/<DS-ID>.schema.json + field table (name, type, unit, null %, example, meaning)
failure modes observed: no key → …; bad param → …; empty → …; timeout → …; 429 → …
quirks: time zone, encoding (Bangla text), IDs, duplicates, sentinel values
mapping to canonical: <entity.field ← raw.field (transform)>
synthetic twin: generator, calibration targets
```

## 2. Registry

### 2.1 Maritime and AIS

| ID | Tier | Source | Access, auth, protocol | Known limits and caveats (verify) | Licence | Use |
|---|---|---|---|---|---|---|
| DS-AIS-01 | P0 | **aisstream.io**, live AIS | Account API key `AISSTREAM_API_KEY`. WebSocket `wss://stream.aisstream.io/v0/stream`. Send the subscription JSON within **3 s**: `APIKey`, `BoundingBoxes`, optional `FiltersShipMMSI` (≤ 200) and `FilterMessageTypes` | ≤ 3 subscribed connections per account; ≤ 3 connections per IP; ≤ 1 subscription update per second; **no SLA, no history** (persist on arrival); slow consumers get messages dropped; **bandwidth limits on uncompressed connections from Sep 2026** (use compression); **server-side only, never from a browser**. Terrestrial coverage of the Bay of Bengal is unknown, so measure it | Check the ToS | Live map; builds our own Chattogram AIS history from day 1 |
| DS-AIS-02 | P0 | **Global Fishing Watch API v3** | Bearer token (free, non-commercial) `GFW_API_TOKEN`; max 5 tokens per account; never embed in a public UI | Events: `public-global-port-visits-events:latest` (**all vessel types**; request short periods). 4Wings: `public-global-presence:latest` (hourly AIS presence, all vessel types, 2012 to ~96 h ago) and `public-global-sar-presence:latest` (SAR detections of industrial vessels, 2017 to ~5 days ago). Vessels: `public-global-vessel-identity:latest`. Daily and monthly request caps are on the "License and Rate Limits" page; record them | **CC BY-NC 4.0** + attribution | **Historical vessel-level port-visit labels for Chattogram**, queue reconstruction, SAR counts |
| DS-AIS-03 | P1 | **Danish Maritime Authority** historical AIS | Free daily CSV zips at `http://aisdata.ais.dk/` (HTTP). The DMA page notes the site is back after a security incident | Large files; download a few days only | Check the DMA policy | Clean full-resolution AIS to develop and validate port-call segmentation and pretraining |
| DS-AIS-04 | P1 | **NOAA MarineCadastre** AIS (US waters) | `github.com/ocm-marinecadastre/ais-vessel-traffic`: 2024 daily point files (GeoParquet, *experimental*), 2024–2025 monthly tracks, 2025 CSV. Older years as daily CSV zips | Large; sample by day and bbox | US public data | A congestion case study (e.g. San Pedro Bay) for pretraining and backtests |
| DS-AIS-05 | P2 | **xView3-SAR** dataset + reference model | Registration on the xView3 site | Labels mostly come from AIS matching | Check | Only if building our own SAR ship detector (stretch) |

### 2.2 Port statistics and geometry

| ID | Tier | Source | Access | Known limits and caveats (verify) | Licence | Use |
|---|---|---|---|---|---|---|
| DS-PORT-01 | P0 | **IMF PortWatch** | No auth. ArcGIS FeatureServer query (`where`, `outFields`, `outSR=4326`, `f=json`, record paging); the example URLs are on `portwatch.imf.org` FAQ/data pages. Also listed on HDX | Daily port calls and trade estimates for ~1.8–2.1k ports (counts differ by source), 28 chokepoints, disruption pages. Built on UN Global Platform AIS. Occasional blackout days; GPS jamming in some regions | IMF terms (`imf-special-terms`); free | Port-level history for Chattogram and Mongla, chokepoint context (Red Sea), calibration |
| DS-PORT-02 | P1 | **UNCTADstat** port-call statistics | Free web/CSV (maritime profile for Bangladesh = code 050) | Median time in port by ship type, per country; derived from MarineTraffic data for ships ≥ 1,000 GT; annual | UNCTAD terms | Calibration targets for the synthetic dwell model |
| DS-PORT-03 | P1 | **World Bank / S&P CPPI** (5th ed., Sep 2025, covering 2020–2024) | PDF/XLSX in the World Bank Open Knowledge Repository | Annual, port-level hours | CC BY (check) | Calibration and demo narrative |
| DS-PORT-04 | P1 | **World Port Index** (NGA Pub 150) | Free download | Port attributes and coordinates | US public | Port reference data |
| DS-PORT-05 | P0 | **UN/LOCODE** (UNECE) | Free download | BDCGP Chattogram, BDMGL Mongla, BDPGN Pangaon confirmed by trackers; **Payra code unverified** | Free | Canonical location IDs |
| DS-PORT-06 | P0 | **OSM via Overpass API** | `https://overpass-api.de/api/interpreter`; fair use, small queries | Port, harbour, quay/pier and `seamark:type=anchorage` features; quality varies | ODbL (attribution; share-alike for derived databases) | Geofences: port limits, anchorages, berths, ICDs |
| DS-PORT-07 | P1 | **Chittagong Port Authority** site (`cpa.gov.bd`), Mongla Port Authority site | Manual probe. Read robots.txt and the ToS first | No indexed daily vessel or berth pages were found. Check what is public (berthing schedule, outer-anchorage list, container position) | Government site | If allowed: real queue counts. Otherwise the press reports the same numbers, which C2 can extract ("news as sensor") |
| DS-PORT-08 | P0 | **searoute** (Python, based on Eurostat MARNET) | Offline package | Approximate sea lanes and distances | MIT (check) | Sea legs, transshipment distances |
| DS-PORT-09 | P1 | **GFW anchorages** (named anchorage points) | GFW data downloads (login) | Global anchorage points derived from AIS | GFW terms | Seed anchorage polygons for Chattogram |

### 2.3 Satellite

| ID | Tier | Source | Access | Caveats (verify) | Use |
|---|---|---|---|---|---|
| DS-SAT-01 | P1 | **Copernicus Data Space Ecosystem**: Sentinel-1 GRD (SAR) and Sentinel-2 L2A | Free account; STAC, OData, openEO and Sentinel Hub APIs (free quotas) | S1 revisit ~6–12 days (Sentinel-1C restored the pair; verify for Bangladesh), all-weather. S2 is cloud-blocked in the monsoon | Validation imagery, ship counts, optional yard-occupancy proxy |
| DS-SAT-02 | P2 | **Microsoft Planetary Computer** STAC (S1 RTC, S2 L2A) | Free, signed URLs | Check that it is still operating in 2026 | Alternative source of the same imagery |
| DS-SAT-03 | P2 | **Google Earth Engine** (non-commercial) | Registration + Cloud project | Quotas | Bulk S1 processing, if needed |
| DS-SAT-04 | P0 | **GFW SAR presence** (see DS-AIS-02) | Token | Industrial vessels; ~5-day latency | **Precomputed** ship detections. Don't build a detector first |

### 2.4 Weather and hazards

| ID | Tier | Source | Access | Caveats (verify) | Use |
|---|---|---|---|---|---|
| DS-WX-01 | P0 | **Open-Meteo**: forecast, historical (`archive-api`) and **Marine** (`marine-api.open-meteo.com/v1/marine`) | No key; free for non-commercial use | Marine: waves, swell, currents, `sea_level_height_msl` (**tides**; verify the method). Check forecast horizons and rate limits | Wind/rain/wave/tide features for C4; routing weather |
| DS-WX-02 | P0 | **GDACS API** | No auth. `https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=TC;FL;EQ&…` returns GeoJSON; Swagger at `/gdacsapi/swagger/index.html` | Credit "Global Disaster Alert and Coordination System, GDACS"; alert levels Green/Orange/Red | Hazard events for C2 and fusion |
| DS-WX-03 | P1 | **IBTrACS** (NOAA NCEI) cyclone tracks | Free CSV/netCDF | Historical | Scenario generation, backtests (e.g. Cyclone Remal, May 2024) |
| DS-WX-04 | P0 | **`holidays` package (BD)** + Islamic calendar | Offline | Eid dates shift each year; verify against official gazette dates | Calendar features, Eid truck-ban windows |

### 2.5 News, events and macro

| ID | Tier | Source | Access | Caveats (verify) | Use |
|---|---|---|---|---|---|
| DS-NEWS-01 | P0 | **GDELT DOC 2.0 API** | No auth. `https://api.gdeltproject.org/api/v2/doc/doc?query=…&mode=ArtList&format=json&maxrecords=250&timespan=…` | Rate-limited (third parties report ~1 request per 5 s; be stricter); check the lookback window; `sourcecountry` codes may be FIPS (Bangladesh = BG) | Article discovery |
| DS-NEWS-02 | P0 | **GDELT 2.0 Events + GKG raw files** | `http://data.gdeltproject.org/gdeltv2/masterfilelist.txt` (15-min files since 2015). BigQuery is optional | Large; filter on ingest (locations BG/IN/CN, themes) | Backfill, themes, locations, organisations, tone |
| DS-NEWS-03 | P0 | **Curated RSS** (see `config/feeds.yaml`): gCaptain, Splash247, Container News, Hellenic Shipping News, The Loadstar (part-paywalled), The Daily Star (Business), The Business Standard (TBS), The Financial Express (BD), Dhaka Tribune, FiercePharma, FDA press releases, Just Style, Textile Today | Per-feed ToS | Store metadata, a snippet and the extracted fields; link out; never republish full text | Bangladesh-specific and industry coverage |
| DS-NEWS-04 | P1 | **ReliefWeb API v2** | **A pre-approved `appname` is required since 1 Nov 2025** (request it on ReliefWeb) | Free | Disaster situation reports |
| DS-NEWS-05 | P2 | **ACLED** | Free registration for non-commercial use; OAuth tokens (new system since Sep 2025); quotas depend on user category | NC + attribution | Strikes, blockades and unrest in the RMG belts |
| DS-NEWS-06 | P1 | **NY Fed GSCPI** | Free monthly CSV/XLSX | Monthly | Macro supply-chain pressure feature |
| DS-NEWS-07 | P2 | **NGA MSI broadcast warnings** | Free | Coverage of the Bay of Bengal | Navigational warnings |

### 2.6 Trade, supply network and risk

| ID | Tier | Source | Access | Caveats (verify) | Use |
|---|---|---|---|---|---|
| DS-TRADE-01 | P1 | **UN Comtrade API** | Free key `COMTRADE_API_KEY`: ~500 calls/day, ≤ 100k records/call (third-party documentation); a no-key preview returns ≤ 500 records | Date-range limits per call | Bangladesh import dependency by HS code and partner (cotton, yarn, fabric, APIs, foil) |
| DS-TRADE-02 | P1 | **CEPII BACI** (HS6 bilateral flows) | Free download | Annual, ~1–2 years behind | Bulk alternative to Comtrade; priors for tier-2 links |
| DS-TRADE-03 | P0 | **World Bank API v2** (WDI, LPI) | No key: `https://api.worldbank.org/v2/country/BGD/indicator/<code>?format=json` | Annual | Country indicators, LPI |
| DS-RISK-01 | P1 | **WGI**, **INFORM Risk Index** (EU JRC), **ND-GAIN** | Free downloads | Annual | Country risk features for C1 |
| DS-RISK-02 | P2 | **WRI Aqueduct floods** / JRC flood hazard maps | Free | Coarse | Facility flood exposure |
| DS-SUP-01 | P1 | **Open Supply Hub** (garment facilities) | Free account: download **≤ 5,000 production locations**. **The API is paid (from $225/month), so it is excluded.** A free or discounted research-access application exists (Q-04) | Facility names are real (see guardrail §5) | Real Bangladesh factory locations and cluster densities |
| DS-SUP-02 | P1 | **SupplyGraph** (Bangladesh FMCG GNN benchmark) | `github.com/CIOL-SUST/SupplyGraph` (mirror: `ciol-researchlab/SupplyGraph`) | Products as nodes; temporal sales, production and factory-issue features | Check | Validates the GNN pipeline on a real Bangladeshi supply graph |
| DS-SUP-03 | P1 | **DataCo Smart Supply Chain** (Kaggle) | Kaggle API token | Orders with a late-delivery-risk label | Check | Delivery-risk baseline; synthetic calibration |
| DS-SUP-04 | P2 | **USAID SCMS Delivery History** (health-commodity shipments) | The Kaggle mirror (the original portal may be gone) | Vendor, manufacturing site, mode, scheduled vs delivered | Check | Pharma supplier delay labels |
| DS-SUP-05 | P2 | **Wikidata SPARQL**, **GLEIF LEI API** | Free | Coverage of Bangladeshi firms is partial | Entity resolution, parent companies |

### 2.7 Pharma regulatory

| ID | Tier | Source | Access | Caveats (verify) | Use |
|---|---|---|---|---|---|
| DS-PHARMA-01 | P0 | **openFDA** | Optional free key `OPENFDA_API_KEY`. Without a key: 240 requests/min and 1,000/day per IP; with a key: 240/min and 120,000/day. `/drug/enforcement.json` (recalls); shortages path to verify (`/drug/shortages.json` vs `/drug/drugshortages.json`); check page-size limits | Free (CC0-like; check) | Recalls and shortages as C2 events and C1 risk labels |
| DS-PHARMA-02 | P1 | **FDA Data Dashboard** (inspection classifications OAI/VAI/NAI, compliance actions, import refusals) | Free API key (verify) | Firm-name matching is fuzzy | US public | Labels for API-manufacturer risk |
| DS-PHARMA-03 | P1 | **FDA Import Alerts** (e.g. 66-40) and **Warning Letters** | Web pages; scrape only if permitted | HTML changes | US public | Supplier risk events |
| DS-PHARMA-04 | P2 | **EudraGMDP** GMP non-compliance; **DGDA** notices | Web | Manual | Public | Extra risk signals |

### 2.8 Geo, routing and emissions

| ID | Tier | Source | Access | Caveats (verify) | Use |
|---|---|---|---|---|---|
| DS-GEO-01 | P0 | **Geofabrik Bangladesh extract** (`download.geofabrik.de/asia/bangladesh.html`) | Free `.osm.pbf` | Road topology errors; missing `maxspeed` | Road, rail and waterway graph |
| DS-GEO-02 | P0 | **Overpass** (see DS-PORT-06) | Fair use | — | ICDs, depots, bridges, toll points |
| DS-GEO-03 | P1 | **OpenRouteService** (HGV profile) | Free key `ORS_API_KEY`; daily and per-minute quotas (record them) | Not for production volume | Calibrating and validating our travel times |
| DS-GEO-04 | P0 | **Nominatim** + **GeoNames dump** | Nominatim: ≤ 1 request/s, identifying User-Agent, cache results; GeoNames: offline | Ambiguous place names | Geocoding for C2; Bangladesh gazetteer |
| DS-GEO-05 | P0 | **Emission factors**: GLEC Framework (ISO 14083 method), **UK DESNZ GHG conversion factors** (annual XLSX) | Free downloads | Choose WTW vs TTW consistently; cite the year | CO2e per tonne-km by mode and vehicle class |
| DS-GEO-06 | P1 | **Bangladesh cost tables**: diesel price (BPC), bridge and expressway tolls, rail and barge tariffs, ICD charges | Manual table with source URL and date | These change often | C3 cost model |
| DS-GEO-07 | P0 | **Basemap tiles**: OpenFreeMap (no key) or Protomaps PMTiles (self-hosted Bangladesh extract) | Free | Attribution required | Map UI |

### 2.9 Vision (C5)

| ID | Tier | Source | Licence (verify) | Use |
|---|---|---|---|---|
| DS-VIS-01 | P0 | **MVTec AD**: `pill`, `capsule`, `carpet`, `leather`, plus others for auxiliary training | **CC BY-NC-SA 4.0** | Zero-shot evaluation; AnomalyCLIP-style auxiliary training |
| DS-VIS-02 | P0 | **VisA**: `capsules`, plus others (`github.com/amazon-science/spot-diff`) | Check (reported CC BY 4.0) | The cross-dataset ZSAD protocol (train on one, test on the other) |
| DS-VIS-03 | P1 | **MVTec LOCO AD** (logical anomalies; packaging analogues) | NC | Blister and packaging logic |
| DS-VIS-04 | P0 | **Fabric/garment**: Fabric Stain Dataset (CC0, ~466 images), figshare "FD dataset" (720 images: oil, hole, cut, crack), Roboflow *StitchNet Defect Detection* (399 images incl. bobbin-thread and overlapped stitches), *Data in Brief* 2025 woven-fabric set (Gil-Arroyo et al.), Carrilho et al. 2024 textile AD set; classic AITEX and ZJU-Leaper (check access) | Per dataset | Garment pack evaluation and demo |
| DS-VIS-05 | P0 | **Pharma**: Roboflow *defective_tablets* (CC BY 4.0: empty, broken, colour-mismatch), *Pharmaceutical Tablet Defects* (230 images, CC BY 4.0), plus MVTec `pill`/`capsule` and VisA `capsules` | Per dataset | Pharma pack evaluation and demo |
| DS-VIS-06 | P2 | **Real-IAD**, **MVTec AD 2** | Check | Harder benchmarks |

### 2.10 Excluded: paid (do not use, even on trial)

MarineTraffic API, VesselFinder API, Spire Maritime, Kpler, Windward, Lloyd's List Intelligence, S&P Panjiva and Global Trade, ImportGenius, project44, FourKites, Sinay, Planet imagery, the Google/TomTom/HERE traffic APIs, the Open Supply Hub API, and NewsAPI.org (its free tier is development-only). UNCTAD's statistics are derived from MarineTraffic but published free, so they are allowed.

## 3. Probe protocol (M0)

1. **Read the docs first.** Fill in the card's auth, limits, licence, ToS, cost and attribution fields before making a call.
2. **Make a minimal meaningful call**, using the smallest window that answers "is this useful for Bangladesh?". For example: the Chattogram outer anchorage bbox for 10 minutes of AIS; port visits at Chattogram for the last 30 days; GDELT articles mentioning Chattogram in the last 7 days.
3. **Save the raw response verbatim** to `data/raw/_probes/<DS-ID>/<UTC-ts>/request.json` (method, URL, params, headers with secrets stripped), `response.<ext>` and `meta.json` (status, headers, latency in ms, bytes, content type, encoding, pagination cursor).
4. **Test failure modes cheaply, once each:** missing or invalid key, bad parameter, empty result, last page of pagination, oversized range, client-side timeout, and the rate-limit headers or 429 body. Never exceed a documented limit to "find" it. If a limit isn't documented, record the headers and stay well under them.
5. **Infer the schema** with `genson`, write it to `schemas/raw/<DS-ID>.schema.json`, and add the field table to the card: units, null %, ID semantics, time zone.
6. **Measure fitness:** Bangladesh coverage (counts in bbox and time window), freshness and latency, history depth, duplicates, sentinel values.
7. **Decide:** status, default mode, and whether the canonical schema in `04-domain-model.md` needs to change. Record the evidence for any change.
8. **Commit small samples** (≤ 5 MB per source) to `data/samples/<DS-ID>/` for replay mode and contract tests. Large raw data stays gitignored.
9. **Summarise** in `PROBE_REPORT.md`.

**Bounding boxes** for probes and the collector, as lon/lat; refine them in M0 from OSM and observed AIS:

| Name | Approx. bbox (lonmin, latmin, lonmax, latmax) | Notes |
|---|---|---|
| `ctg_outer_anchorage` | 91.50, 21.70, 91.95, 22.30 | Outer anchorage, the Karnaphuli approach and Kutubdia lighterage. Verify the anchorage polygons (Alpha/Bravo/Charlie are commonly cited) |
| `ctg_port_river` | 91.76, 22.22, 91.86, 22.36 | Karnaphuli berths (CCT, NCT, PCT, GCB). Verify the terminal operators |
| `mongla` | 89.40, 21.60, 89.70, 22.55 | Pussur channel and anchorage |
| `payra` | 90.15, 21.65, 90.45, 22.10 | Rabnabad channel |
| `bay_of_bengal_approach` | 88.0, 19.5, 92.5, 22.5 | Arrivals and ETA modelling (high volume; filter by message type) |

## 4. Synthetic data strategy

Synthetic data fills the gaps where no free real data exists. It must use the **same schema**, be calibrated to real statistics, be deterministic (seeded), be scenario-driven, and be labelled `is_synthetic` with a `scenario_id`. Replace it source by source.

| Gap | Generator (`packages/sim`) | Calibrate to |
|---|---|---|
| Suppliers, factories, warehouses, products, BOMs, orders, inventory | `world.py`: fictional firms at real clusters (Gazipur, Ashulia/Savar incl. DEPZ, Narayanganj incl. Adamjee EPZ, CEPZ, Karnaphuli EPZ, Mongla EPZ; pharma in Savar, Gazipur and the API park at Gazaria, Munshiganj); real ports and ICDs | Comtrade/BACI shares by HS code and partner; Open Supply Hub cluster densities; SupplyGraph temporal patterns |
| Vessel-level history at Chattogram | `port_des.py` (SimPy): arrivals (liner schedule + noise), tidal windows and draught/LOA limits (verify the current CPA rules), berth classes, weather and cyclone closures, Eid slowdowns, yard-congestion feedback. **It emits AIS-like position streams with gaps and noise plus ground-truth port calls** | GFW port visits (durations by type), PortWatch daily calls, UNCTAD median time in port, CPPI, press-reported queue sizes, our own aisstream recordings |
| Rail and barge services | Timetable and capacity generator | 2025 press facts (trains per month, demand of 6–7 per day; three barges on the Pangaon run) |
| Production batches and quality | Beta-binomial defect rates with line, shift, supplier and drift effects. **Images are always real dataset images mapped to fictional SKUs** | AQL norms; dataset defect ratios |
| Disruptions | `scenarios.py` library: cyclone, strike or blockade, customs outage, rail shortage, Red Sea diversion, supplier fire, Eid ban; each with ground-truth effects | IBTrACS/GDACS history; press timelines |

**Calibration report.** `docs/data-sources/CALIBRATION.md` compares synthetic and real marginals (quantiles, KS statistic) for every calibrated quantity, and is regenerated by `make calibrate`.

## 5. Guardrails

- **Real names, real facts only.** A real firm (e.g. from Open Supply Hub) may appear only with attributes that came from a source. Synthetic risk, defect or delay values go on **fictional** entities only (Q-05).
- **Respect licences:** keep NC data (GFW, MVTec, ACLED) out of anything presented as commercial, and attribute it on the Data & Models page and in the README.
- **News copyright:** store the URL, title, ≤ 300-character snippet, extracted fields and evidence spans. Full text is transient (used for extraction, then dropped) unless the licence allows keeping it.
- **Respect rate limits:** use a central token bucket per DS-ID in `connectors/base.py`; cache everything; use an identifying User-Agent of the form `Cportal/0.1 (+contact)`.
