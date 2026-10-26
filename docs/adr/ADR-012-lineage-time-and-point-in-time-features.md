# ADR-012: Lineage, time and point-in-time features

Status: accepted   Date: 2026-10-26

**Context:** sources lag from minutes (GDACS) to ten days (PortWatch); SC-01 asked for an
`available_at` column. The brief's lineage column `mode` collides with the transport `mode`
columns on lane, supply_edge, shipment_leg and emission_factor (A-032).

**Decision:** Every domain table carries `source_id`, `source_record_id`, `data_mode`,
`is_synthetic`, `scenario_id`, `generator_version`, `ingested_at`, `available_at`,
`created_at`, `updated_at`. `available_at` is the source's publication time, else event time
plus the measured lag, else fetch time; features filter on it so backtests cannot peek past
`as_of`. The database enforces `is_synthetic = (data_mode = 'synthetic')` and that synthetic
rows carry a scenario. Times are UTC `timestamptz`, displayed in Asia/Dhaka.

**Alternatives considered:** event time only (silent look-ahead in backtests); a separate
lineage table (joins on every read).

**Consequences:** + honest backtests; + synthetic data cannot pass as real at the database level.
− `data_mode` differs from the brief's column name (documented here and in DECISIONS).
