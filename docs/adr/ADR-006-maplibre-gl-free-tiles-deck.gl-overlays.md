# ADR-006: MapLibre GL + free tiles; deck.gl overlays

Status: accepted   Date: 2026-10-26

**Context:** the Control Tower map and route views need vector tiles without a token. DS-GEO-07
verified OpenFreeMap's TileJSON 3.0 and MapLibre style v8, with attribution (contract-tested).

**Decision:** MapLibre GL JS with OpenFreeMap tiles (attribution shown), deck.gl layers for vessels,
routes and heatmaps. A self-hosted Protomaps extract of Bangladesh is the offline fallback for
the demo.

**Alternatives considered:** Mapbox/Google (tokens, paid tiers); raster OSM tiles (usage policy
forbids heavy use).

**Consequences:** + free and fast. − The offline extract must be built before the final demo (M8).
