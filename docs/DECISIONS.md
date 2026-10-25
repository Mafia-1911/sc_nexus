# Decisions and assumptions

Every answer from the user and every assumption the agent made (template: `docs/brief/07-decisions.md` §3).
Settled user decisions D-01…D-10 live in the brief; architectural choices get an ADR in `docs/adr/`.

| Date | ID | Decision / assumption | Why | Reversible? | Asked user? |
|------|----|------------------------|-----|-------------|-------------|
| 2026-10-26 | Q-04 | Keys provided: aisstream, GFW, Roboflow, UN Comtrade, openFDA, plus NASA Earthdata (not in the brief) | User added them to `.env` during M0 | yes | yes (user action) |
| 2026-10-26 | U-01 | Where a source fails (no coverage, 429s, timeouts) use synthetic data with the same schema and keep building the backbone | User directive mid-M0, after aisstream showed no Bangladesh coverage | yes | yes (user directive) |
| 2026-10-26 | U-02 | **Two strikes:** never retry a failing API, timeout or search more than twice; fall back to synthetic (same or near-same schema) or another open dataset; MVP first. "Scrape" stays within robots.txt/ToS (AGENTS.md rule 2) | User directive mid-M0 | yes | yes (user directive) |
| 2026-10-26 | A-001 | Installed uv 0.13.5 user-level (`~/.local/bin`, no shell-profile edits) and a uv-managed Python 3.12.15 | uv was missing; the brief mandates `uv run probe` and Python 3.12 (system has 3.14) | yes | no (required by brief) |
| 2026-10-26 | A-002 | Import names `cportal_core` and `cportal_connectors` (src layout, uv_build); capability packages keep `c1_supplier_graph` etc. | Bare `core`/`connectors` risk collisions with stray top-level packages in site-packages | yes | no (default) |
| 2026-10-26 | A-003 | uv `link-mode = "copy"` | The repo is on NTFS; hardlinks from the uv cache on another filesystem fail | yes | no |
| 2026-10-26 | A-004 | Probe evidence layout: `data/raw/_probes/<DS-ID>/<UTC-ts>/<call>/{request.json,response.<ext>,meta.json,fields.json}` + `summary.json` + a `LATEST` pointer file | 03 §3 step 3 describes one call; probes make several (main + failure modes) | yes | no |
| 2026-10-26 | A-005 | One raw schema file per DS-ID with a `$defs` entry per call (`schemas/raw/<DS-ID>.schema.json`) | Several endpoints per source; reruns update entries in place | yes | no |
| 2026-10-26 | A-006 | Source cards are generated (`make cards`) from `docs/data-sources/cards.yaml` + `config/sources.yaml` + the latest probe run | Keeps 47 cards consistent with evidence; numbers never retyped | yes | no |
| 2026-10-26 | A-007 | Registry gains a `fallback` field and a `manual` status (human-maintained table with citations) | Encodes U-02 per source; DS-GEO-06 is a cited manual table by design | yes | no |
| 2026-10-26 | A-008 | Settings accept the user's variable names as aliases and tolerate quoted names in `.env`; `.env` values are never printed | User's `.env` predates `.env.example`; renaming their file is intrusive | yes | no |
| 2026-10-26 | A-009 | UN/LOCODE from `unlocode.unece.org` (Pre-Release zip) instead of `service.unece.org` | The brief's host serves a Cloudflare JS challenge to every client (bypassing it would breach ToS) | yes | no |
| 2026-10-26 | A-010 | Financial Express BD excluded; FiercePharma marked blocked | FE's robots.txt disallows AI crawlers (ClaudeBot, GPTBot, CCBot, anthropic-ai); FiercePharma returns 403 bot walls | yes | no (respects rule 2) |
| 2026-10-26 | A-011 | Committed news samples keep metadata + ≤ 300-char snippets only; committed AIS samples are 5 real frames per message type | News-copyright guardrail (03 §5); aisstream publishes no terms on redistribution | yes | no |
| 2026-10-26 | A-012 | Synthetic AIS twin v0 (`ais_synthetic.py`, `uv run ais-synth`): aisstream frame format, MMSIs with MID 999, names "SYN …", priors in `config/priors/ds_ais_01_synthetic.yaml` calibrated to PortWatch and GFW | U-01; aisstream has zero Bangladesh coverage. The SimPy port DES (packages/sim, M1) replaces its visit planner | yes | yes (U-01) |
| 2026-10-26 | A-013 | GDELT raw files (DS-NEWS-02) are C2's primary discovery path; DOC API is a later, best-effort secondary | DOC returned 429 on the first request three times (two strikes) | yes | no |
| 2026-10-26 | A-014 | Geofences and inland POIs to be extracted locally from the Geofabrik PBF, not Overpass (ADR in M1) | Overpass: 30–114 s per query, 502 at capacity, mirror timed out (two strikes) | yes | no (proposed for G0) |
| 2026-10-26 | A-015 | Anchorage zones come from GFW anchorage cells, not OSM | OSM has no anchorage features around Chattogram | yes | no (proposed for G0) |
| 2026-10-26 | A-016 | CO2e factors from UK DESNZ 2026 (OGL) with the GLEC/ISO 14083 method; GLEC default values not used | GLEC v3.2 default values are restricted to SFC members and certified tools | yes | no |
| 2026-10-26 | A-017 | `config/areas.yaml` adds `bangladesh`, `dhaka_region`, `dhaka_ctg_corridor` envelopes beside the brief's bboxes | Country-wide Overpass regexes time out; coverage counts need a country envelope | yes | no |
| 2026-10-26 | A-018 | TLS verification is never disabled; `.gov.bd` sites with broken chains stay blocked for scripts | cpa.gov.bd serves a certificate for another domain; turning verification off would be unsafe | yes | no |
| 2026-10-26 | A-019 | AIS collector writes verbatim frames to hourly JSONL, gzipped on rotation; Parquet conversion and Postgres "latest position" come with the worker in M2 | M0 has no DB; the raw zone must be immutable and verbatim | yes | no |
| 2026-10-26 | A-020 | NC sources (GFW, CPPI, MVTec) probed and flagged, nothing NC shipped yet | Q-06 still open; probing is data access only | yes | pending Q-06 |
| 2026-10-26 | A-021 | Git initialised; brief committed on `main`, M0 work on branch `m0-recon` | AGENTS.md asks for frequent commits; branch keeps `main` clean until G0 | yes | no |
| 2026-10-26 | A-022 | Lint: ruff `allowed-confusables` for en dash, ×, typographic quotes; RUF012 ignored in `sources/*` | Deliberate typography in user-facing text; connector class attributes are declarative config | yes | no |
