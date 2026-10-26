# STATUS (updated 2026-10-26 BST by Claude Code, Opus 5.5)

Milestone: **M1 Architecture complete → gate G1 (soft: summary posted, work continues unless
the user objects).** Next: M2 Backbone (hard gate G2).

Done (M1, branch `m1-architecture`):
- Domain model v1: 51 tables (SQLAlchemy 2 + GeoAlchemy2 + pgvector) with lineage on every
  domain table (`data_mode`, `available_at`, …) and the SC-01…SC-12 changes; one Alembic
  migration (round-trip tested); generated [ERD](ERD.md).
- Canonical records (37 Pydantic types) contract-tested against the tables; idempotent loader
  (deterministic UUIDv5 ids, coalescing upserts).
- Parsers for every P0 source plus the CPA berthing PDF, ReliefWeb; `uv run ingest --replay
  all` loads 24 sources (all real, offline) with FKs intact.
- `packages/sim`: world v0 (fictional firms at real clusters, golden-path structure, orders,
  DCSA shipments, AQL batches), name packs (Q-05 guardrail), SimPy port DES with real CPA
  berths, tides, channel slots, lighterage and lighters, calibrated: dwell KS D 0.097 vs GFW,
  presence 71.7 vs 70.7 ([CALIBRATION.md](data-sources/CALIBRATION.md)).
- Twins for 11 sources render each wire format through the real parsers; scenarios
  `baseline` and `cyclone_supplier_delay` with projection KPIs; `make seed` ≈ 30 s (< 60 s).
- `apps/api`: 31 OpenAPI paths, `{data, meta}` envelope with LIVE/REPLAY/SYNTHETIC/mixed
  badges, scenario scope, problem+json, cursor pagination, 202 jobs, read p95 < 300 ms.
- docker-compose (db with PostGIS + pgvector, migrate, api, seed) written and validated;
  not built yet (Docker socket permission).
- ADR-001…014; decisions up to A-043; import-linter boundary contracts; 206+ tests green.

In progress:
- Nothing half-written.

Next (M2, ordered):
1. Worker: APScheduler, outbox consumer, jobs (`job.queued`), live fetch for verified sources
   with the two-strikes fallback; AIS Parquet lake.
2. Web shell (Next.js App Router, Tailwind v4, shadcn/ui, Tidewater tokens from 05-ui-design):
   Control Tower (MapLibre map of the anchorage, KPI strip, alert feed stub), Data & Models.
3. Generated TS types from `docs/api/openapi.json`; `/ws/live` streaming positions.
4. Compose: worker + web; `make up && make seed && make demo`; Playwright smoke test.

Blockers (owner: user):
- Docker socket: `sudo usermod -aG docker $USER`, then log out and in. Needed to build and run
  compose (G2). Until then the local Postgres (`make db-local`) runs everything.
- Ollama (or llama.cpp) for C2 in M4 (Q-03): not installed yet; not needed for M2.

Waiting on user:
- Confirm the Q-05 guardrail default (real names never on adverse synthetic attributes).
- Optional: more CPA berthing PDFs into `data/inbox/DS-PORT-07/` (real berth-level labels).

Data modes: DS-AIS-01=synthetic (no Bangladesh coverage), DS-AIS-02=replay, DS-SAT-04=replay,
DS-PORT-01=replay, DS-PORT-05=replay, DS-PORT-07=replay (manual PDFs), DS-WX-01=live,
DS-WX-02=live, DS-WX-05=live, DS-NEWS-02=live, DS-NEWS-03=live, DS-NEWS-04=live,
DS-PHARMA-01=live, DS-TRADE-03=live, DS-GEO-03=live, DS-GEO-07=live; M1 loads every source in
replay mode from its committed samples.

Model versions active: none (baselines register from M3).

Demo health: golden path not built yet (M8). Scenario `cyclone_supplier_delay` seeds; its port
effect is modest in DES v0 (+3.8 % vessel-hours, hero vessel +13.8 h) until M6 backtests Remal.
