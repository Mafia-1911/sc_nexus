@AGENTS.md

## Session quick start (Claude Code)

- Read `handoff.md` first: repo map, the Tariff Monitor (C6), how to change the UI, how to make
  cross-layer changes, build/test/deploy, gotchas, and a copy-paste start prompt (§9).
- Then `docs/STATUS.md` for the current state; load brief files only per AGENTS.md §6.
- Capabilities: C1 `/network`, C2 `/radar`, C3 `/routes`, C4 `/ports`, C5 `/quality`,
  C6 tariffs `/tariffs` (ADR-021, `docs/tariffs/`), Nexus `/scenarios` and Control Tower `/`.
- Key commands: `make demo` (Docker stack + seed), `make check` (lint, types, tests, web),
  `make e2e` (Playwright + axe on :3000), `make openapi` then `cd apps/web && npm run gen:api`
  after any API change, `uv run c6 refresh` after tariff data or migration changes.
- UI work: use the ui-consistency skills; tokens from `apps/web/app/globals.css`; a data badge on
  every data surface; verify at 1280 px in light and dark.
- Git: commit on `m3-c1` only; never force-push or hard-reset; if the remote moved, merge FETCH_HEAD.
