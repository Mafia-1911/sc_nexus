# STATUS (updated 2026-10-26 05:55 BST by Claude Code, Opus 5.5)

Milestone: M0 Recon complete. **Waiting at gate G0** for the user's review.

Done (this session):
- Repo skeleton: uv workspace (`packages/core`, `packages/connectors`), `config/sources.yaml`,
  `config/feeds.yaml`, `config/areas.yaml`, `.env.example`, Makefile, README; git with `main` + `m0-recon`.
- Probe harness: `uv run probe <DS-ID>` saves request/response/meta, infers JSON Schema, profiles
  fields, copies samples, redacts secrets, rate-limits per source; cards regenerate offline.
- Probed all 24 P0 and all 22 P1 sources (+ proposed DS-SAT-05 NASA Earthdata): 32 verified,
  8 need a sign-up or a human step, 7 blocked. 47 cards + `docs/data-sources/PROBE_REPORT.md`.
- AIS: collector (`make collect-ais`) built and run (~50 min, 0 Bangladesh messages); synthetic
  twin (`make synth-ais`) in the exact aisstream format, calibrated to PortWatch + GFW.
- Tests: 37 passing (harness, redaction, decoders, settings, AIS twin contract vs real frames);
  ruff and mypy clean.

In progress:
- AIS collector still running in this session's background (coverage watch); it stops when the
  session ends. Restart any time with `make collect-ais`.

Next (ordered, after G0):
1. ADR-001…010 + ADR-011 (two-strikes fallback), ADR-012 (`available_at` lineage) per the accepted schema changes.
2. Domain model v1: SQLAlchemy models + Alembic migrations (needs Docker), Pydantic schemas, `external_id`.
3. Connector `parse()` → canonical rows for P0 sources in replay mode from `data/samples/`, contract tests real ↔ synthetic.
4. `packages/sim`: world v0 (fictional firms at real clusters) + SimPy port DES v0 replacing the AIS twin's planner; `CALIBRATION.md`.
5. OpenAPI skeleton (all routers, stub responses with `meta`).

Blockers:
- Docker not installed (user) — needed for Postgres/PostGIS/pgvector in M1 and compose in M2.

Waiting on user: G0 go-ahead; Q-01, Q-02, Q-03, Q-05, Q-06, Q-07, Q-08, Q-09; schema changes SC-01…SC-12;
"needs you" list in PROBE_REPORT.md.

Data modes (proposed defaults): DS-AIS-01=synthetic, DS-AIS-02=replay, DS-SAT-04=replay,
DS-PORT-01=replay, DS-PORT-05=replay, DS-WX-01=live, DS-WX-02=live, DS-NEWS-02=live,
DS-NEWS-03=live, DS-PHARMA-01=live, DS-TRADE-03=live, DS-GEO-07=live (others in config/sources.yaml).

Model versions active: none (M0).

Demo health: golden path not built yet (M8).
