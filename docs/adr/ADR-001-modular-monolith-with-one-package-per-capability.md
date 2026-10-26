# ADR-001: Modular monolith with one package per capability

Status: accepted   Date: 2026-10-26

**Context:** D-06 asks for one db, one api, one worker and one web app, with five modelling
pipelines that stay independently testable. M1 has core, connectors, sim and api; C1–C5 land
from M3.

**Decision:** A uv workspace with `packages/core` (shared kernel), `packages/connectors`,
`packages/sim`, `apps/api`, and later `packages/c1_…c5_*`, `packages/nexus`, `apps/worker`,
`apps/web`. The import rule (02 §4) is enforced by import-linter in `make lint`: core imports
no other Cportal package; connectors import only core; the API never imports the generators or
connectors (it reads the database). The API is the `cportal_api` package (src layout), run as
`uvicorn cportal_api.main:app`, instead of the brief's `apps.api.main` module path: src layouts
keep packages importable only through their declared dependencies.

**Alternatives considered:** microservices per capability (more moving parts on a laptop, no
measured need); one flat package (boundaries erode, capabilities stop being separable).

**Consequences:** + independent tests and future extraction (`uv run cN serve`); + boundaries
checked in CI. − Cross-capability data flows through tables, the outbox or a typed
`service.py`, which takes a little more ceremony. Revisit if a capability needs its own
process for a measured reason.
