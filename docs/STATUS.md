# STATUS (updated 2026-10-26 20:20 BST by Claude Code, Opus 5.5)

Milestone: **M1 Architecture, starting.** G0 approved 2026-10-26 (all kickoff questions answered,
SC-01…SC-12 accepted). G1 is a soft gate (summary, then continue unless the user objects).

Done (this session, after G0):
- Recorded the G0 answers Q-01…Q-09 and new assumptions A-023…A-029 in `docs/DECISIONS.md`.
- Probed the new credentials, all verified:
  - DS-NEWS-04 ReliefWeb (18,063 Bangladesh reports, 113 disasters)
  - DS-GEO-03 OpenRouteService (HeiGIT key; Chattogram → Kamalapur 244.8 km)
  - DS-VIS-01 MVTec AD via the Kaggle mirror (5.27 GB, still CC BY-NC-SA 4.0)
  - new proposed DS-WX-05 NASA FIRMS active fires (MAP_KEY, 5,000 transactions per 10 min)
- DS-PORT-07 is now `manual`: the CPA berthing report PDF the user downloaded (2026-01-05; 41 rows,
  26 with IMO numbers, named berths, tide table) is a committed replay sample.
- Settings: aliases for the user's new `.env` names; `CPORTAL_BRAND_NAME` (Q-07),
  `CPORTAL_NAME_PACK` (Q-05), `DATABASE_URL`, `LLM_BASE_URL`/`LLM_MODEL` (Q-03).
- Local Postgres 16 + PostGIS 3.5 + pgvector installed user-level (A-023) so migrations can be
  tested before Docker works.
- Cards regenerated (48), PROBE_REPORT tables refreshed plus an "Update after G0" section,
  `docs/SESSION_LOG.md` started, everything pushed to github.com/Mafia-1911/sc_nexus.

In progress (M1, branch `m1-architecture`):
- Nothing half-written. Next steps below are ordered.

Next (ordered):
1. ADR-001…010 plus ADR-011 (two-strikes fallback), ADR-012 (`available_at` lineage), ADR-013
   (local OSM extraction instead of Overpass), ADR-014 (name packs and brand variable).
2. Domain model v1 in `packages/core`: enums, IDs, lineage mixin, SQLAlchemy 2 + GeoAlchemy2 +
   pgvector models, Pydantic schemas, Alembic migrations (`db/alembic`), ERD in `docs/`.
3. Connector `parse()` → canonical rows for every P0 source (replay from `data/samples/`) plus a
   synthetic twin per source; contract tests real ↔ synthetic ↔ canonical; CPA PDF parser.
4. `packages/sim`: world v0 (fictional firms at real clusters, garments hero, pharma variant; name
   packs including the real-name `bd_demo` pack from a web search), SimPy port DES v0 replacing
   the AIS twin's planner, scenarios (cyclone + supplier delay), `CALIBRATION.md`.
5. `apps/api` OpenAPI skeleton (every router, stub responses with `meta`, brand in `/api/v1/meta`).
6. `docker-compose.yml` + `db/Dockerfile` (PostGIS + pgvector), `make up/seed/db-local`.
7. G1 summary.

Blockers:
- Docker 29.9 + Compose v5.6 are installed, but the socket is not accessible: the user is not in
  the `docker` group (user: `sudo usermod -aG docker $USER`, then log out and back in). Until
  then M1 uses the local Postgres; M2 (`docker compose up`) needs it.
- Copernicus CDSE login not working (user retrying; DS-SAT-04 GFW SAR covers the need).

Waiting on user:
- Confirm the Q-05 guardrail: with the real-name pack, keep adverse synthetic attributes (defects,
  recalls, supplier failures, risk scores) on fictional names? (Default until answered: yes.)

Data modes: DS-AIS-01=synthetic (no Bangladesh coverage), DS-AIS-02=replay, DS-SAT-04=replay,
DS-PORT-01=replay, DS-PORT-05=replay, DS-PORT-07=replay (manual PDFs), DS-WX-01=live,
DS-WX-02=live, DS-WX-05=live, DS-NEWS-02=live, DS-NEWS-03=live, DS-NEWS-04=live,
DS-PHARMA-01=live, DS-TRADE-03=live, DS-GEO-03=live, DS-GEO-07=live (others in config/sources.yaml).

AIS collector: stopped with the earlier session after 85 min (22:59–00:24 UTC) with 0 vessel
messages; `make collect-ais` restarts it.

Model versions active: none (M1).

Demo health: golden path not built yet (M8).
