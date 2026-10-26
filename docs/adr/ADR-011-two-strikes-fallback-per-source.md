# ADR-011: Two-strikes fallback per source

Status: accepted   Date: 2026-10-26

**Context:** user directives U-01/U-02: never retry a failing API, timeout or search more than
twice; keep building on same-schema synthetic or other open data.

**Decision:** `config/sources.yaml` records `mode` and `fallback` per DS-ID. After two failures a
source switches to its fallback (replay of the last good sample, another source, or its
synthetic twin) and the card says why. The worker (M2) applies this automatically and shows it
on the Data & Models page.

**Alternatives considered:** retry with backoff until success (stalls the demo; violates U-02).

**Consequences:** + the demo never depends on one flaky endpoint. − Fallback data must be clearly
badged (it is: `meta.mode`).
