# ADR-002: Postgres 16 + PostGIS + pgvector as the single store

Status: accepted   Date: 2026-10-26

**Context:** relational, geographic and vector data (02 §5); one store for the demo laptop. Docker
was not usable during M1, so a user-level Postgres from conda-forge serves dev and tests
(A-023); compose uses `postgis/postgis:16-3.5` plus the PGDG pgvector package.

**Decision:** One Postgres 16 database with PostGIS 3.5 and pgvector. Geometry is `geometry` in
SRID 4326 with GiST indexes; distance work casts to `geography`. The supply graph lives in
tables (`facility`, `supply_edge`, `bom_edge`) and is computed in NetworkX/PyG in memory.
Enums are VARCHAR validated by Pydantic (A-033); primary keys are deterministic UUIDv5 where
a natural key exists (A-034), so ingests and seeds are idempotent upserts. Embeddings are
384-dim `vector` columns with HNSW (article, organization).

**Alternatives considered:** Neo4j/Apache AGE for the graph (no graph-native query need at this
size); SQLite/DuckDB only (no concurrent writes, weak geo indexing for the API).

**Consequences:** + one backup, one connection pool, joins across domains. − Large AIS history
must not live here (ADR-003). Revisit at > 1M graph edges or Cypher-shaped queries.
