# ADR-010: Connector modes live, replay and synthetic through the same parsers

Status: accepted   Date: 2026-10-26

**Context:** D-08 (probe first, same schema in all modes) and 02 §8.

**Decision:** Each source module declares `parsers` (sample → parser) and `record_types`. Replay
parses committed samples (`Connector.replay()`, `uv run ingest --replay`); live fetching reuses
the same parsers in M2; synthetic twins render the source's own wire format and call the same
parser with a synthetic ParseContext. Canonical records (`cportal_core.schemas.records`) are
the single schema, contract-tested against the ORM tables and against each source's replay
and twin output (lineage, types, units). Sources without rows (basemap) declare `checks`.
vcrpy cassettes are deferred: committed samples already serve replay.

**Alternatives considered:** separate synthetic generators that write rows directly (schemas
drift; parsers go untested on synthetic data).

**Consequences:** + switching a source's mode is configuration; + parser bugs surface on both
real and synthetic data. − Twins must emit plausible wire formats, which takes care.
