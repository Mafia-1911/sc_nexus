# 00 · Brief index

**TL;DR.** This folder is the full specification for Cportal / Supply Chain Nexus. Each file opens with a short summary and can be read on its own. Load files by task (see `AGENTS.md` §6), never all at once. Treat the brief as read-only. If something here is wrong, propose an edit in `docs/DECISIONS.md` and ask the user.

## Files

| File | What it holds | Read it when |
|---|---|---|
| `01-product.md` | Problem, Bangladesh context, personas, industry packs, golden-path demo, KPIs, non-goals | Scoping, UX copy, demo prep |
| `02-architecture.md` | Principles, system diagram, repo layout, stack, pipeline contract, notebook flow, eventing, budgets, reuse-or-build table, seed ADRs | Any structural work |
| `03-data-sources.md` | Source registry (DS-IDs), access, limits, licences, probe protocol, source-card template, synthetic-data strategy | M0, connectors, ingestion, any data question |
| `04-domain-model.md` | Shared entities, ID standards, table sketch, lineage columns, event topics, API conventions | Schemas, migrations, APIs |
| `05-ui-design.md` | Oceanic design tokens (validated), layout, pages, map, graph and chart rules, accessibility, demo polish | Any frontend work |
| `06-roadmap.md` | M0–M8, tasks, acceptance criteria, gates, hackathon cut lines, demo script | Planning, start and end of each milestone |
| `07-decisions.md` | Decisions made (D-xx), open questions (Q-xx) with defaults, ADR/STATUS/DECISIONS templates | Kickoff, whenever unsure |
| `08-nexus-layer.md` | Scenario engine, evidence fusion, recommendations, shipment tracking, brief/copilot, backtesting | M8, and any cross-capability hook |
| `capabilities/C1-supplier-graph.md` | Supplier risk graph | M3 |
| `capabilities/C2-trade-news.md` | Trade-news intelligence | M4 |
| `capabilities/C3-routing.md` | Multimodal routing | M5 |
| `capabilities/C4-port-dwell.md` | Vessel dwell and port congestion | M6 |
| `capabilities/C5-defect-intel.md` | Defect intelligence | M7 |

## ID scheme

| Prefix | Meaning | Example |
|---|---|---|
| `D-xx` | Decision already made by the user | D-04: vessel dwell is the C4 target |
| `Q-xx` | Open question with a default. `ask-at:` says when to raise it | Q-03: LLM policy |
| `ADR-nnn` | Architecture decision record, written by the agent | ADR-002: Postgres instead of Neo4j |
| `DS-<DOMAIN>-nn` | Data source | DS-AIS-01: aisstream.io |
| `Cn-Rxx` / `Cn-ACxx` | Requirement or acceptance criterion of capability *n* | C4-AC03 |
| `NX-Rxx` / `NX-ACxx` | Nexus-layer requirement or acceptance criterion | NX-AC02 |
| `M0`–`M8`, `G0`–`G3` | Milestones and hard gates | G2 |
| `K-xx` | Platform KPI | K-03: alert lead time |

## Capability file template

Every `capabilities/C*.md` file has the same sections, so you can jump straight to the one you need:

1. Job to be done (user stories)
2. Hackathon scope (Must / Should / Stretch)
3. Inputs (DS-IDs; real vs synthetic)
4. Output contract (tables, events, API)
5. Method ladder (baseline → advanced → innovative)
6. Models and libraries (with CPU and notebook notes)
7. Evaluation and acceptance criteria
8. API endpoints
9. UI
10. Integration hooks
11. Risks, guardrails, open questions

## Conventions

- Words like "verify" or "(verify)" mark facts gathered by desk research on 2026-10-26 that M0 probing must confirm. Never treat them as settled.
- Times are UTC in storage and Asia/Dhaka (UTC+6) on screen.
- Every number shown to a user carries its source and mode (LIVE, REPLAY or SYNTHETIC).
