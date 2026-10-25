# M0 probe report (G0)

Probed 2026-10-25/26 UTC from a residential connection in Bangladesh (Cloudflare PoP: Dhaka),
with `uv run probe` (`packages/connectors`). Every number below comes from a saved probe run;
each source card in this folder links the evidence, the inferred raw schema
(`schemas/raw/<DS-ID>.schema.json`) and committed samples (`data/samples/<DS-ID>/`).

## TL;DR

- **All 24 P0 and all 22 P1 sources were probed**, plus one source not in the brief (NASA
  Earthdata, for which the user supplied a token): 32 are usable as-is, 8 need a sign-up or a
  human step, and 7 are blocked (2 of them P0: GDELT DOC and MVTec AD). Every blocked or
  unreliable source has a same-schema fallback in `config/sources.yaml` (the two-strikes rule).
- **AIS: aisstream has zero coverage around Bangladesh** (0 messages in 10 min plus ~50 min of
  collector runtime over the Bay of Bengal approach, while the key streamed 44 msg/s worldwide).
  Global Fishing Watch fills the gap with real, vessel-level history: 1,897 Chattogram port
  visits in 90 days and 60–80 cargo ships a day in the outer anchorage, 2–4 days behind real time.
  A **synthetic AIS twin** (`uv run ais-synth`) emits frames in exactly aisstream's format,
  calibrated to PortWatch and GFW, so the backbone can be built now and switched to live data
  without code changes.
- **News: the GDELT DOC API is blocked from this network** (HTTP 429 on the first request, three
  times). The GDELT raw 15-minute files work and already carry Bengali-language sources through
  GDELT's translation stream; 11 curated RSS feeds work.
- **Several brief facts were wrong** and are corrected in the registry: the UN/LOCODE host, the
  Payra code (it is BDPAY), CPPI and searoute licences, World Port Index coverage, dead MVTec
  links, and the dead TBS / stale Daily Star feeds. See [Surprises](#surprises).
- **Proposed schema changes**: twelve, each with evidence (§[Schema](#proposed-changes-to-the-canonical-schema)).
  The biggest: an `available_at` lineage column (sources lag 0–10 days), port-call stops with
  anchorage/dock cells, an `external_id` table, and daily port activity and zone presence tables.

## Summary: P0 sources

| DS-ID | Tier | Status | Mode → fallback | Auth | Limits | Licence (NC) | Bangladesh coverage | Freshness | History |
|---|---|---|---|---|---|---|---|---|---|
| [DS-AIS-01](DS-AIS-01.md) | P0 | verified | synthetic → synthetic | api-key | 3 subscribed connections per account and per IP; | No terms page found (only /privacypolicy). | None. 0 messages in 10 min over the Bay of Bengal approach box (88.0–92.5 E, 19.5–22.5 N) and 0 in about 50 min of collector runtime (two runs, 2026-10-25 22:5… | real time (seconds) where receivers exist | none (persist on arrival) |
| [DS-AIS-02](DS-AIS-02.md) | P0 | verified | replay → synthetic | bearer-token | 50,000 requests/day and 1,500,000/month across all tokens; | CC BY-NC 4.0; non-commercial use only (NC) | Strong. 1,897 port visits at `bgd-chittagong` in 90 days (1,242 cargo, 1,662 at confidence 4); | port visits and presence ≈ 2–4 days behind (latest presence day 2026-10-21, lat… | port visits back to 2012+ (visits overlapping the window are returned, some sta… |
| [DS-PORT-01](DS-PORT-01.md) | P0 | verified | replay → synthetic | none | none published; ArcGIS Online fair use | IMF PortWatch terms (free use with attribution; | 5 ports: Chittagong port241 (mean 6.36 calls/day 2019–2026, max 22; | Daily_Ports_Data ends 2026-10-16 when probed on 2026-10-26 (10-day lag) | 2019-01-01 onward, one row per port per day (2,846 days) |
| [DS-PORT-05](DS-PORT-05.md) | P0 | verified | replay → replay | none | none; a 13 MB zip per release | UN/CEFACT standards are free to use under CC BY 4.0 (unlocode.unece.org footer) | 45 Bangladesh codes: 12 ports (BDCGP Chattogram 2220N 09150E, BDMGL Mongla (no coordinates), BDPAY Payra Port (confirms the code), BDPGN Pangaon, BDPCR Panchas… | Pre-Release (Latest) zip dated 2026-10-23 | official releases biannual (latest official 2025-1 on UNICC GitLab) |
| [DS-PORT-06](DS-PORT-06.md) | P0 | verified | replay → DS-GEO-01 | none | ~10,000 requests and 1 GB per day per user; | ODbL 1.0 (share-alike for derived databases) | Chattogram envelope: 123 features (100 piers, 6 docks, 5 harbours, 'Patenga Container Terminal Jetty', 'Matarbari Deep Sea Port', operator 'Red Sea Gateway Ter… | minutely diffs (osm_base 2026-10-25T22:46Z) | — |
| [DS-PORT-08](DS-PORT-08.md) | P0 | verified | live → live | none | offline; first route 791 ms (graph load), then < 13 ms | Apache-2.0 (searoute 1.6.0 package metadata; | BDCGP → Colombo 1,334 nm, Singapore 1,528 nm, Port Klang 1,341 nm, Rotterdam 8,092 nm, Los Angeles 9,313 nm; | — | — |
| [DS-SAT-04](DS-SAT-04.md) | P0 | verified | replay → synthetic | bearer-token | as DS-AIS-02; 4Wings date range ≤ 366 days (HTTP 422 beyond) | CC BY-NC 4.0 (NC) | Outer anchorage, last 120 days: 28 overpass days, 50–251 detections per pass (Sentinel-1 roughly every 4 days) | latest detection day 2026-10-17 when probed on 2026-10-26 (~9 days) | 2017 onward |
| [DS-WX-01](DS-WX-01.md) | P0 | verified | live → replay | none | free non-commercial use < 600 calls/min, 5,000/hour, 10,000/day, 300,000/month | CC BY 4.0 (data); non-commercial free tier | forecasts and marine data at both Chattogram points; | forecasts updated hourly; archive ~5-day delay (ERA5) | weather archive from 1940; marine via ERA5-Ocean (0.5°) for history |
| [DS-WX-02](DS-WX-02.md) | P0 | verified | live → replay | none | none; pass `caller` to identify the client | free; credit "Global Disaster Alert and Coordination System, GDACS" | 17 events with Bangladesh since 2019: TC 9 (Red: Fani-19, Bulbul-19, Amphan-20, Hamoon-23; | minutes to hours | events since 2000s |
| [DS-WX-04](DS-WX-04.md) | P0 | verified | live → manual | none | — | MIT (holidays 0.107) | 17–23 public holidays per year 2019–2027; | — | — |
| [DS-NEWS-01](DS-NEWS-01.md) | P0 | blocked | False → DS-NEWS-02 | none | informal: "Please limit requests to one every 5 seconds" (the API's own 429 body) | GDELT terms (free; cite GDELT) | not measured (blocked) | — | — |
| [DS-NEWS-02](DS-NEWS-02.md) | P0 | verified | live → replay | none | none (static files); BigQuery optional | GDELT terms (free; cite "The GDELT Project") | 24 h of Events: 63,040 events, 370 located in Bangladesh (0.6 %), mostly Dhaka; | 15-minute batches | since 2015 (masterfilelist) |
| [DS-NEWS-03](DS-NEWS-03.md) | P0 | verified | live → replay | none | per-feed robots.txt; crawl-delay 30 s (Hellenic Shipping News, FDA), 10 s (TBS) | per-publisher copyright; store URL, title, ≤ 300-char snippet only (committed samples are… | 260 items from 11 active feeds; 133 mention Bangladesh terms (Dhaka Tribune 100, Textile Today 12, Daily Star business 4, TBS economy 4) | most feeds < 5 h old at probe time; Splash247, Loadstar, Just Style ~60 h (week… | last 8–100 items per feed (no backfill; GDELT supplies history) |
| [DS-TRADE-03](DS-TRADE-03.md) | P0 | verified | live → replay | none | ≤ 60 indicators per request, URL ≤ 4,000 chars; | CC BY 4.0 (most WDI series) | LPI overall only for 2007, 2010, 2014, 2016, 2018, 2022 (latest 2.6); | lastupdated 2026-10-08 | annual from 1960 |
| [DS-PHARMA-01](DS-PHARMA-01.md) | P0 | verified | live → replay | optional-api-key | no key 240/min and 1,000/day per IP; with key 240/min and 120,000/day | openFDA (public domain / CC0-like) | 109 drug recalls by Indian firms in 2025–2026 (Class II 91, III 8, I 1); | last_updated 2026-10-14 | — |
| [DS-GEO-01](DS-GEO-01.md) | P0 | verified | replay → replay | none | — | ODbL 1.0 | whole country; PBF 355,878,537 bytes; Shapefile 975 MB; | data cut-off 2026-10-24T20:20:51Z; daily updates | dated extracts back to 2014 (yearly snapshots) |
| [DS-GEO-02](DS-GEO-02.md) | P0 | verified | replay → DS-GEO-01 | none | as DS-PORT-06 | ODbL 1.0 | 26 container sites by name (ICD / depot / terminal), 191 toll booths (some in India: clip to the BD polygon), 154 rail stations in the corridor box (incl. | — | — |
| [DS-GEO-04](DS-GEO-04.md) | P0 | verified | live → replay | none | Nominatim ≤ 1 request/s, identifying User-Agent, cache results, no bulk or autocomplete; | Nominatim results ODbL; GeoNames CC BY 4.0 | All six test places found (Chattogram Port 5, Kamalapur ICD 2, Pangaon 1, Mongla Port 5, Payra Port 1, Dhaka EPZ 1). | GeoNames BD edited 2026-10-24 | — |
| [DS-GEO-05](DS-GEO-05.md) | P0 | verified | replay → replay | none | — | UK Open Government Licence v3.0 (DESNZ); | factors are UK-based (no Bangladesh-specific values); | 2026 set published 2026-06-11, flat file revised July 2026 | — |
| [DS-GEO-07](DS-GEO-07.md) | P0 | verified | live → replay | none | OpenFreeMap public instance has no limits on views; | OpenMapTiles schema, OSM data (ODbL); commercial use allowed | vector tiles to z14 over the Karnaphuli berths (z8 95 KB, z12 68 KB, z14 43 KB) | weekly planet builds (tiles dated 20261018) | — |
| [DS-VIS-01](DS-VIS-01.md) | P0 | blocked | False → DS-VIS-02 | none | — | CC BY-NC-SA 4.0; "not allowed to use the dataset for commercial purposes" (NC) | n/a (benchmark images) | — | — |
| [DS-VIS-02](DS-VIS-02.md) | P0 | verified | replay → replay | none | one 1,929,840,640-byte tar from S3; split CSV 10,821 rows | CC BY 4.0 (LICENSE-DATASET); code Apache-2.0 | n/a | — | — |
| [DS-VIS-04](DS-VIS-04.md) | P0 | verified | replay → DS-VIS-02 | mixed | StitchNet v4: 483 images, classes Skipped stitch 97, normal 102, Stain and damage 102, Overlapped stitch 101, bobbin thread defect 97 | StitchNet CC BY 4.0; Fabric Stain CC0 (Kaggle/Dataset Ninja); | n/a (garment pack images) | — | — |
| [DS-VIS-05](DS-VIS-05.md) | P0 | verified | replay → DS-VIS-02 | api-key | defective_tablets v3: 919 images (broken 339, spotted 427, empty 250, color_mismatch 487); | CC BY 4.0 (per project) | n/a (pharma pack images) | — | — |

## Summary: P1 sources

| DS-ID | Tier | Status | Mode → fallback | Auth | Limits | Licence (NC) | Bangladesh coverage | Freshness | History |
|---|---|---|---|---|---|---|---|---|---|
| [DS-AIS-03](DS-AIS-03.md) | P1 | blocked | False → DS-AIS-04 | none | large daily CSV zips; DMA site was offline after a security incident (brief) | DMA terms (not reached) | n/a (Danish waters; used only to develop port-call segmentation) | — | — |
| [DS-AIS-04](DS-AIS-04.md) | P1 | blocked | False → synthetic | none | — | US public data | n/a (US waters) | — | — |
| [DS-PORT-02](DS-PORT-02.md) | P1 | blocked | False → manual | none | — | UNCTAD terms; derived from MarineTraffic (ships ≥ 1,000 GT) but published free | country-level medians (not probed: the data viewer renders client-side) | — | — |
| [DS-PORT-03](DS-PORT-03.md) | P1 | verified | replay → manual | none | — | CC BY-NC 3.0 IGO (the brief assumed CC BY) (NC) | Chattogram is ranked in the index (port-level hours; | — | annual; editions 2020–2024 (published 2025-09-22) and CPPI 2025 (published 2026… |
| [DS-PORT-04](DS-PORT-04.md) | P1 | verified | False → DS-PORT-05 | none | whole index (2,951 ports) in one 6.3 MB JSON; | US public (NGA) | None. No Bangladesh (or Sri Lanka) entries; | — | — |
| [DS-PORT-07](DS-PORT-07.md) | P1 | blocked | False → synthetic | none | — | — | unknown (sites unreachable to scripted clients) | — | — |
| [DS-PORT-09](DS-PORT-09.md) | P1 | needs-registration | False → DS-AIS-02 | account-download | — | GFW terms (non-commercial) (NC) | the same anchorage IDs and positions already arrive inside port-visit events (9 anchorage cells and 4 dock cells around Chattogram in config/priors) | — | — |
| [DS-SAT-01](DS-SAT-01.md) | P1 | needs-registration | False → DS-SAT-04 | account | free quotas per account (record on sign-up) | Copernicus data licence (free and open, attribution "Contains modified Copernicus Sentine… | Last 60 days over the outer anchorage: Sentinel-1 GRD 25 items on 15 days (all sentinel-1d); | hours after acquisition | — |
| [DS-SAT-05](DS-SAT-05.md) | P1 | needs-registration | False → DS-WX-02 | bearer-token | — | NASA data are open (no restrictions; cite the product) | 14 MCDWD_L3_NRT (MODIS NRT flood) granules over Bangladesh in 10 days via CMR; | — | — |
| [DS-WX-03](DS-WX-03.md) | P1 | verified | replay → replay | none | — | NOAA NCEI (public domain; cite IBTrACS v04r01) | Storms within 2° of the approach box in the last 3 years: Mocha, Hamoon, Midhili (2023), Remal, Dana (2024), plus unnamed systems | last3years file has provisional fixes up to the probe day (2026-10-25) | North Indian basin since the 1800s (full file); |
| [DS-NEWS-04](DS-NEWS-04.md) | P1 | needs-registration | False → DS-WX-02 | appname | — | free (per-report source licences) | — | — | — |
| [DS-NEWS-06](DS-NEWS-06.md) | P1 | verified | replay → replay | none | — | free (Federal Reserve Bank of New York; cite Benigno et al.) | global index (not country-specific) | — | — |
| [DS-TRADE-01](DS-TRADE-01.md) | P1 | verified | replay → DS-TRADE-02 | api-key | free key ≈ 500 calls/day, ≤ 100,000 records/call; | UN Comtrade terms (free; cite UN Comtrade) | Bangladesh last self-reported in 2018. Mirror data works: 2024 India→BD cotton (HS 52) $2.70 B, China→BD cotton $2.28 B, knitted fabric (60) $1.98 B, staple fi… | — | — |
| [DS-TRADE-02](DS-TRADE-02.md) | P1 | verified | replay → DS-TRADE-01 | none | release V202601; BACI_HS22 zip 2.05 GB | CEPII terms (free for research; Etalab Open Licence 2.0 for BACI) | all reporters and partners, HS6 (mirror-reconciled) | — | — |
| [DS-RISK-01](DS-RISK-01.md) | P1 | verified | replay → replay | none | INFORM 2026 workbook 2.5 MB; ND-GAIN 2026 zip link found | WGI CC BY 4.0; INFORM (EC JRC, free with citation); | country-level for Bangladesh and supplier countries | — | — |
| [DS-SUP-01](DS-SUP-01.md) | P1 | needs-registration | False → synthetic | account-download | — | CC BY-SA 4.0 for OSH data (check on download); | — | — | — |
| [DS-SUP-02](DS-SUP-02.md) | P1 | verified | replay → synthetic | none | — | LGPL-2.1 on the repository (code licence applied to data; | Bangladesh FMCG company graph (products, plants, product groups); | — | last push 2025-01-15 |
| [DS-SUP-03](DS-SUP-03.md) | P1 | verified | replay → synthetic | none | — | CC BY 4.0 (Mendeley Data v5, 2019) | none (global e-commerce orders); used only for delivery-risk baselines and synthetic calibration | — | — |
| [DS-PHARMA-02](DS-PHARMA-02.md) | P1 | needs-registration | False → DS-PHARMA-01 | api-key | — | — | — | — | — |
| [DS-PHARMA-03](DS-PHARMA-03.md) | P1 | verified | replay → DS-PHARMA-01 | none | fda.gov robots.txt Crawl-Delay 30; accessdata.fda.gov does not disallow /cms_ia | US public | Import Alert 66-40 page (1.96 MB) mentions India 120 times, China 166, Bangladesh 0 | — | — |
| [DS-GEO-03](DS-GEO-03.md) | P1 | needs-registration | False → DS-GEO-01 | api-key | — | — | — | — | — |
| [DS-GEO-06](DS-GEO-06.md) | P1 | manual | replay → manual | none | — | — | — | — | — |
| [DS-VIS-03](DS-VIS-03.md) | P1 | blocked | False → DS-VIS-05 | none | — | CC BY-NC-SA 4.0 (NC) | — | — | — |

**Not probed (P2, by design):** DS-AIS-05 xView3-SAR, DS-SAT-02 Planetary Computer, DS-SAT-03
Earth Engine, DS-NEWS-05 ACLED, DS-NEWS-07 NGA MSI warnings, DS-RISK-02 Aqueduct/JRC floods,
DS-SUP-04 USAID SCMS, DS-SUP-05 Wikidata/GLEIF, DS-PHARMA-04 EudraGMDP/DGDA, DS-VIS-06 Real-IAD,
MVTec AD 2.

## Surprises

Facts in the brief that the probes contradicted (registry updated; logged in `docs/DECISIONS.md`):

| # | Brief said | Probe found | Evidence |
|---|---|---|---|
| S1 | aisstream terrestrial coverage of the Bay of Bengal unknown | **None**: 0 messages over 88.0–92.5 E, 19.5–22.5 N | [DS-AIS-01](DS-AIS-01.md) |
| S2 | UN/LOCODE at service.unece.org | Cloudflare JS challenge on every URL; **unlocode.unece.org** serves the zip directly, CC BY 4.0 | [DS-PORT-05](DS-PORT-05.md) |
| S3 | Payra code unverified | **BDPAY** "Payra Port" (status AA, 2156N 09016E) | [DS-PORT-05](DS-PORT-05.md) |
| S4 | GDELT DOC ~1 request/5 s | 429 on the first request after minutes idle, three times | [DS-NEWS-01](DS-NEWS-01.md) |
| S5 | Overpass for geofences | 30–114 s per query, 502 at capacity; **no anchorage features at Chattogram** in OSM | [DS-PORT-06](DS-PORT-06.md) |
| S6 | World Port Index has port attributes | Current NGA API has **no Bangladesh (or Sri Lanka) entries** | [DS-PORT-04](DS-PORT-04.md) |
| S7 | CPPI "CC BY (check)", 5th edition latest | **CC BY-NC 3.0 IGO**; a newer **CPPI 2025** was published 2026-06-10 | [DS-PORT-03](DS-PORT-03.md) |
| S8 | searoute "MIT (check)" | Apache-2.0 | [DS-PORT-08](DS-PORT-08.md) |
| S9 | MVTec AD downloadable | pill, capsule, carpet and the full archive **404**; only leather works | [DS-VIS-01](DS-VIS-01.md) |
| S10 | "Pharmaceutical Tablet Defects (230 images)" | 32 source images (230 after augmentation) | [DS-VIS-05](DS-VIS-05.md) |
| S11 | figshare "FD dataset (720 images)" | Not found anywhere | [DS-VIS-04](DS-VIS-04.md) |
| S12 | TBS and Daily Star in the RSS list | Their top-level feeds are dead (2021) or stale and malformed; section feeds work | [DS-NEWS-03](DS-NEWS-03.md) |
| S13 | Comtrade gives Bangladesh's imports | Bangladesh last self-reported in **2018**; only mirror data (partners' exports) is current | [DS-TRADE-01](DS-TRADE-01.md) |
| S14 | Port authority sites may publish queues | cpa.gov.bd serves a certificate for afccl.gov.bd without its chain (also mpa, bpc, biwtc) | [DS-PORT-07](DS-PORT-07.md) |
| S15 | `holidays` covers Eid | Only the core 3 days; extended Eid closures and truck bans are missing | [DS-WX-04](DS-WX-04.md) |
| S16 | PortWatch LOCODEs usable as keys | Null for Chittagong and Payra; others written with a space ("BD MGL") | [DS-PORT-01](DS-PORT-01.md) |
| S17 | GFW port visits give anchorage wait vs berth | 1,142 of 1,159 cargo visits stop only at anchor cells (lighterage); OVERLAP mode returns multi-year "visits" | [DS-AIS-02](DS-AIS-02.md) |
| S18 | Open-Meteo marine forecast ≤ 8 days | 16 days accepted; river points snap to a sea cell ~10 km away | [DS-WX-01](DS-WX-01.md) |
| S19 | GDACS country filter | Takes the name ("Bangladesh"); ISO3 and empty results return **204**, `eventsbyarea` hangs | [DS-WX-02](DS-WX-02.md) |
| S20 | GLEC default emission factors | Restricted to SFC members; DESNZ 2026 factors (OGL) used with the GLEC method | [DS-GEO-05](DS-GEO-05.md) |

## Blockers

| Blocker | Impact | Owner | Mitigation in place |
|---|---|---|---|
| **Docker is not installed** on this machine | M1 migrations need Postgres 16 + PostGIS + pgvector; M2 needs `docker compose up` | user | Install Docker Engine + Compose plugin (or approve a native Postgres install) before M1 work on the DB |
| aisstream has no Bangladesh coverage | No live AIS for the Control Tower map | — | Synthetic twin (same frame format) + GFW replay; collector kept for other regions |
| GDELT DOC API returns 429 from this IP | No keyword search API for C2 | — | GDELT raw files (working) + RSS; retry DOC from a cloud worker later |
| Overpass overloaded | Slow geofence/ICD extraction | — | Extract the same tags locally from the Geofabrik PBF in M1 |
| MVTec AD/LOCO links dead | Pharma benchmark images | user (optional) | VisA capsules + Roboflow defective_tablets (both CC BY 4.0) |
| Bangladesh `.gov.bd` sites fail TLS | No CPA queue numbers, BPC diesel prices by script | user (manual check) | Press numbers via C2; manual cost table with citations |
| 95 %-full drive (50 GB free, NTFS) | Large downloads (BACI 2 GB, VisA 1.9 GB, PBF 0.36 GB) | user | Download per milestone; keep raw data outside git |

## Needs you

| Priority | What | Where | Env var | Unblocks |
|---|---|---|---|---|
| 1 | Install Docker Engine + Compose plugin | https://docs.docker.com/engine/install/ | — | M1 DB work, M2 |
| 2 | Answer the open kickoff questions (Q-01, Q-02, Q-03, Q-05, Q-06, Q-07, Q-08, Q-09) | this chat | — | M1 scope, licences |
| 3 | Request a ReliefWeb appname (approval takes days) | https://apidoc.reliefweb.int/parameters#appname | `RELIEFWEB_APPNAME` | DS-NEWS-04 |
| 4 | OpenRouteService key (optional, C3 validation) | https://openrouteservice.org/dev/#/signup | `ORS_API_KEY` | DS-GEO-03 |
| 5 | Copernicus Data Space account (optional, Q-15) | https://dataspace.copernicus.eu | (CDSE login) | DS-SAT-01 downloads |
| 6 | Kaggle account/token (optional, Fabric Stain dataset) | https://www.kaggle.com/settings | `KAGGLE_USERNAME`, `KAGGLE_KEY` | part of DS-VIS-04 |
| 7 | Open the MVTec AD downloads page in a browser; tell me whether pill/capsule links work there | https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads | — | DS-VIS-01 |
| 8 | Check cpa.gov.bd in a browser: is a berthing schedule or outer-anchorage list public, and do its terms allow automated reading? | https://cpa.gov.bd | — | DS-PORT-07 |
| 9 | Say what the NASA Earthdata token is for (flood maps? Sentinel-1 at ASF?); LANCE NRT needs its own app key | https://nrt3.modaps.eosdis.nasa.gov | `EARTHDATA_TOKEN` (+ LANCE key) | proposed DS-SAT-05 |
| 10 | Open Supply Hub account, only if Q-05 (b) | https://opensupplyhub.org | — | DS-SUP-01 |

Already provided and verified: `AISSTREAM_API_KEY`, `GFW_API_TOKEN`, `COMTRADE_API_KEY`,
`OPENFDA_API_KEY`, `ROBOFLOW_API_KEY` (and `EARTHDATA_TOKEN`, see row 9).

## Proposed changes to the canonical schema

Against `docs/brief/04-domain-model.md` (draft). Each needs your OK at G0; accepted ones become
ADR-0xx in M1.

| # | Change | Why (evidence) |
|---|---|---|
| SC-01 | Add **`available_at`** (when the record became available to us) to the lineage columns, next to `ingested_at`, and make every feature query filter on it | Sources lag very differently: GDACS minutes, GFW presence 2–4 days, GFW SAR ~9 days, PortWatch 10 days, Open-Meteo archive ~5 days. Point-in-time features (02 §8 "never peek past `as_of`") need publication time, not event time |
| SC-02 | New **`external_id`** table `(entity_type, entity_id, scheme, value, valid_from, valid_to)` instead of ever more ID columns | One port already has five IDs that disagree: BDCGP (UN/LOCODE), `port241` (PortWatch, LOCODE null), `bgd-chittagong` (GFW), GeoNames, OSM. PortWatch writes LOCODEs with a space |
| SC-03 | `port_call`: add `visit_kind` (`berth_call` / `anchorage_only`), `gfw_visit_id`, `confidence` (2–4), and a child **`port_call_stop`** `(port_call_id, seq, cell_id, at_dock, lat, lon, start_ts, end_ts)` | GFW visits carry start/intermediate/end anchorage cells with `atDock`; 1,142 of 1,159 cargo visits never reach a dock (lighterage). Vessel dwell (D-04) = anchorage wait + berth time must be computable for both kinds |
| SC-04 | `port_call.quality_flags`: standard flags `long_stay` (> 60 d), `window_overlap`, `low_confidence` | GFW OVERLAP mode returned a 12-year "visit" at dock; p90 of raw durations is 1,331 h vs 276 h after filtering |
| SC-05 | `port_zone`: allow `zone_type = anchorage_cell | dock_cell` with `cell_id` (GFW anchorage ID) and point/cell geometry; `source` required | OSM has **no** anchorage polygons at Chattogram; GFW gives 9 anchorage and 4 dock cells with visit counts |
| SC-06 | New **`port_activity_daily`** `(port_id, date, calls_by_type jsonb, import_t, export_t)` | PortWatch daily series since 2019-01-01 for 5 Bangladesh ports; the main calibration target for arrivals |
| SC-07 | New **`zone_presence_daily`** `(zone_id, date, vessel_id, vessel_type, hours, mean_sog_kn, entry_ts, exit_ts)` (Parquet; aggregates in `port_state_snapshot`) | GFW 4Wings presence: 3,624 vessel-days in 40 days for the outer anchorage with IMO/MMSI/type; the only real queue-length signal |
| SC-08 | Canonical AIS position: `ts` (receiver `time_utc`) **and** `received_at`; `msg_type`; sentinels mapped to null (Cog 360, TrueHeading 511, RateOfTurn -128, Sog 102.3); `vessel.flag_iso3` | aisstream `time_utc` is Go-formatted with ns; GFW flags are ISO3; MMSI arrives as int (aisstream) or string (GFW `ssvid`) |
| SC-09 | `disruption_event.external_ids` jsonb (`gdacs`, `fda_recall`, `import_alert`) and `alert_level` | GDACS IDs are stable across episodes and PortWatch's disruptions layer reuses them; openFDA recall numbers are the natural key |
| SC-10 | `article`: add `discovered_via` (`gdelt_gkg`, `gdelt_doc`, `rss`), `feed_id`, `source_lang` (from GKG `srclc`) | DOC API blocked, so GKG + RSS are the discovery paths; 38 Bengali-source records in 2 h of the translation stream |
| SC-11 | New **`trade_flow`** `(reporter, partner, hs6, year, flow, value_usd, net_wgt_kg, is_mirror, source)` | Bangladesh stopped self-reporting to Comtrade after 2018; C1 priors must come from mirror flows (e.g. India→BD cotton $2.70 B in 2024) |
| SC-12 | New **`holiday`** `(date, kind: public | extended_closure | truck_ban, name, notice_url, source)` and **`emission_factor`** `(mode, vehicle_class, fuel, unit, ghg_unit, value, scope, year, source)` | `holidays` misses extended Eid closures and truck bans; DESNZ 2026 factors come as 3,658 freight rows with TTW/WTT split |

Kept as drafted: UN/LOCODE as the location key (confirmed 45 BD codes), MMSI MID 405 for
Bangladesh, `is_synthetic` + `scenario_id` on every row (the twin already emits them), DCSA and
EPCIS alignment (no evidence against it in M0).

## Calibration targets measured (for the M1 synthetic world and port DES)

| Quantity | Value | Source |
|---|---|---|
| Chattogram calls/day by type (2026-06-27..10-16) | container 3.62, tanker 1.22, dry bulk 0.61, general 0.50, ro-ro 0.07; total 6.02 (sd 2.07) | DS-PORT-01 |
| Chattogram calls/day, 2019–2026 mean | 6.36 (max 22) | DS-PORT-01 |
| Cargo port time, conf 4, < 60 d (90 d window) | p10 32 h, p50 83 h, p90 276 h | DS-AIS-02 |
| Vessels present in the outer anchorage per day | 80–128 all types; 57–81 cargo | DS-AIS-02 (4Wings presence) |
| Busiest anchorage cells | (22.095, 91.795) 1,430 visits; (22.131, 91.737) 997; (21.731, 91.781) 529 | DS-AIS-02 |
| SAR detections per Sentinel-1 pass (anchorage) | 50–251, about every 4 days | DS-SAT-04 |
| Container port traffic | 3,353,732 TEU (2024) | DS-TRADE-03 |
| Cyclones within 2° of the approach box, 2023–2025 | Mocha, Hamoon, Midhili, Remal, Dana + unnamed | DS-WX-03 |
| GDACS Bangladesh events since 2019 | 17 (TC 9, FL 6, EQ 2) | DS-WX-02 |
| Bangladesh-located GDELT events | 370 per day (0.6 % of 63,040) | DS-NEWS-02 |

The synthetic AIS twin v0 reproduces the median port time (81.8 h vs 83 h) but not the tail
(p90 182 h vs 276 h) nor the anchorage population (29–36 vs 57–81 cargo vessels, because
lighters and coasters are not modelled yet). M1's DES must close both gaps before it drives a KPI.

## Method and reproducibility

- `uv run probe <DS-ID>` runs the source's probe module (`packages/connectors/src/cportal_connectors/sources/`),
  saving `request.json`, `response.<ext>` and `meta.json` per call under
  `data/raw/_probes/<DS-ID>/<UTC-ts>/` (gitignored), merging the inferred JSON Schema into
  `schemas/raw/`, profiling fields, and copying samples (≤ 5 MB per source, news trimmed to
  metadata and ≤ 300-character snippets, AIS limited to 5 format fixtures per type).
- Secrets are redacted by name and by value before anything touches disk; the User-Agent is
  `Cportal/0.1 (Supply Chain Nexus research prototype)`.
- Politeness: a token bucket per source from `config/sources.yaml` (GDELT 10 s, Overpass 5 s,
  Nominatim 1.1 s, others 1–2 s), a one-hour re-probe guard, crawl-delays from robots.txt, no
  limit ever exceeded on purpose, at most two attempts per failing source.
- Cards regenerate offline from the latest runs: `make cards`.
