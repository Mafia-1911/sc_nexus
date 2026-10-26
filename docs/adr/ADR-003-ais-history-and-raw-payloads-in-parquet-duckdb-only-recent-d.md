# ADR-003: AIS history and raw payloads in Parquet + DuckDB; only recent data in Postgres

Status: accepted   Date: 2026-10-26

**Context:** aisstream has no Bangladesh coverage (PROBE_REPORT S1), but the collector and the
synthetic twin both emit high-volume frames (~200k frames per simulated week).

**Decision:** Raw responses stay verbatim in `data/raw/` (immutable, gitignored); position history
goes to Parquet partitions queried with DuckDB (M2 worker). Postgres holds the latest position
per vessel (`ais_position_latest`, forward-only upserts) and derived port calls. GFW 4Wings
presence (`zone_presence_daily`, ~30k rows a year) stays in Postgres although SC-07 suggested
Parquet: it is small and the API reads it directly (A-031).

**Alternatives considered:** TimescaleDB (another extension to operate); all positions in Postgres
(bloats the database the API reads).

**Consequences:** + cheap history, fast map reads. − Two stores for AIS; training extracts read
Parquet. Revisit if real Bangladesh AIS volume appears.
