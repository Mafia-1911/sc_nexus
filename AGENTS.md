# AGENTS.md: Cportal (Supply Chain Nexus)

Standing brief for any coding agent (Antigravity, Claude Code, Codex, Cursor). Kept under 12k characters on purpose. Detail lives in `docs/brief/`. Load only the files the current task needs (section 6).

## 1. Mission

Build **Supply Chain Nexus** (repo codename **Cportal**), a supply-chain resilience platform. It turns data about ships, ports, suppliers, trade news and factory quality into decisions that cut port delay, raise resilience and speed up delivery. Prove it end to end on Bangladesh's **Chattogram to Dhaka** corridor for **garment (RMG)** and **pharma** shippers.

After the shared backbone, build five capabilities in this order:

| ID | Capability | The question it answers |
|---|---|---|
| C1 | Supplier risk graph | Which suppliers and ports do many products depend on, and what breaks if one fails? |
| C2 | Trade-news intelligence | What disruption happened, where, to whom, for how long, and how much buffer should we add? |
| C3 | Routing optimisation | What is the fastest, cheapest or lowest-CO2e way from port or ICD to warehouse, and how likely is it to arrive on time? |
| C4 | Port dwell prediction | When will this vessel berth and leave (P10/P50/P90), and how congested will Chattogram be next week? |
| C5 | Defect intelligence | Which items and batches are defective, and which orders and deliveries does that put at risk? |

The **Nexus layer** ties them together: scenarios, evidence fusion, recommendations and shipment tracking. See `docs/brief/08-nexus-layer.md`.

## 2. Your role

You are the senior software architect, ML engineer, data engineer and technical project planner. Design one coherent platform. Keep the five modelling pipelines independently testable and deployable.

## 3. Decisions already made (do not re-ask)

| ID | Decision |
|---|---|
| D-01 | **Bangladesh first.** Chattogram (BDCGP), Mongla (BDMGL) and Payra ports; Dhaka, Gazipur, Savar and Narayanganj clusters; export lanes via Colombo and Singapore. Other countries' open data may be used to train models. |
| D-02 | **Hackathon horizon (weeks).** A polished end-to-end demo comes first. Prefer pretrained and zero-shot models over training from scratch. |
| D-03 | **Compute.** Train in free Colab or Kaggle notebooks and export the weights. The app runs CPU-only inference. |
| D-04 | **The C4 target is vessel dwell** (anchorage wait plus berth time). Container dwell comes later, as a derived estimate. |
| D-05 | **Stack.** FastAPI, SQLAlchemy 2, Pydantic v2, psycopg 3, Postgres 16 with PostGIS and pgvector, Next.js (App Router), Tailwind v4 and shadcn/ui, docker-compose. This matches the user's existing projects. |
| D-06 | **Modular monolith:** `db`, `api`, `worker`, `web`. Any new service needs an ADR that gives a concrete reason. |
| D-07 | **No paid APIs or data.** Free tiers that need registration are allowed. Record each one in the source registry. |
| D-08 | **Probe first.** Call each real source, save the raw responses, design the schemas from them, then build the backbone on synthetic data with the same schemas. Swap in real data one source at a time. |
| D-09 | **Order:** backbone, then C1, C2, C3, C4, C5, then Nexus integration and demo polish. |
| D-10 | **UI:** calm, oceanic, clean and modern. The tokens are in `docs/brief/05-ui-design.md`. |

## 4. Hard rules

1. **Ask, don't assume** (section 7). Defaults in the brief are not permission to guess outside it.
2. **No paid sources.** No scraping against ToS or robots.txt. Respect rate limits: cache, back off and identify yourself with a User-Agent.
3. **Never present synthetic data as real.** Every row carries `is_synthetic`, and the UI shows a LIVE, REPLAY or SYNTHETIC badge. Synthetic companies get fictional names. Never attach synthetic risk scores or defects to real, named firms.
4. **Reuse open source before building.** Build only what doesn't exist (the reuse-or-build table is in `02-architecture.md` §9), and justify anything new in an ADR.
5. **Models earn their place.** Each one ships with a simple baseline, a model card and an evaluation on a time-based holdout. A complex model replaces the baseline only if it beats it. Report honest numbers, including failures.
6. **Pipelines stay independent.** `packages/cN_*` import only `packages/core`. They talk to each other through DB tables, outbox events or a typed `service.py`, never by reaching into each other's internals.
7. **CPU budget.** Interactive API reads stay under 300 ms at p95. Anything heavy runs as a worker job, and demo-critical results are precomputed.
8. **Secrets** live only in `.env`, never in git, logs or the browser. Server-side keys (aisstream, GFW) are never exposed to the client.
9. **Track licences** for every dataset and model in the registry and model cards. Flag non-commercial (NC) licences such as GFW, MVTec and ACLED.
10. **Keep docs current:** `docs/STATUS.md` every session, an ADR for each architectural choice, and `docs/DECISIONS.md` for every assumption you made.

## 5. Plan and stop gates

| Milestone | Output | Gate |
|---|---|---|
| M0 Recon | Repo skeleton, probes of every P0 source, `PROBE_REPORT.md`, `config/sources.yaml`, kickoff questions answered | **G0: stop and review** |
| M1 Architecture | Domain model fixed from the probe evidence, ADRs, migrations, OpenAPI skeleton, synthetic world v0 with calibration report, contract tests | **G1: stop and review** |
| M2 Backbone | `docker compose up` brings up a themed dashboard shell, the Control Tower (live or replayed AIS map), Data & Models page, worker jobs, outbox and e2e smoke test | **G2: stop and review** |
| M3–M7 | C1 to C5, each as a thin end-to-end slice first, then deepened | Soft gate per capability: summarise, then ask whether to go deeper or move on |
| M8 Nexus and demo | Scenario Studio, evidence fusion, golden-path script, performance work, README, video | **G3: final review** |

Do not implement C1 to C5 before G2. Day-level plan, cut lines and acceptance criteria: `docs/brief/06-roadmap.md`.

## 6. Retrieval map (load only what you need)

| Task | Read |
|---|---|
| Any session start | `docs/STATUS.md`, then the rows below for your task |
| Product context, demo story, KPIs | `docs/brief/01-product.md` |
| Architecture, repo layout, stack, contracts | `docs/brief/02-architecture.md` |
| Data sources, probing, synthetic data | `docs/brief/03-data-sources.md` |
| Entities, IDs, DB tables, events, API rules | `docs/brief/04-domain-model.md` |
| UI, theme tokens, pages | `docs/brief/05-ui-design.md` |
| Milestones, acceptance criteria, cut lines | `docs/brief/06-roadmap.md` |
| Decisions, open questions, templates | `docs/brief/07-decisions.md` |
| Cross-capability features | `docs/brief/08-nexus-layer.md` |
| Building C1 to C5 | `docs/brief/capabilities/C{n}-*.md` |

Stable IDs make the brief greppable: `D-xx` decisions, `Q-xx` questions, `DS-XXX-nn` data sources, `Cn-Rxx` requirements, `Cn-ACxx` acceptance criteria, `ADR-nnn`, `M0`–`M8`, `G0`–`G3`. Reference these IDs in commits, docs and code comments where useful.

## 7. Ask, don't assume

- **Ask before** anything costly to reverse or user-facing: schema-shaping choices, scope cuts, licences or ToS, account sign-ups or credentials, anything that contradicts this brief, and any choice listed as a `Q-xx` in `07-decisions.md`.
- **Don't ask** about reversible implementation details the brief already covers. Pick the documented default and log it in `docs/DECISIONS.md`.
- **Format:** batch your questions, at most four at a time. For each one give the `Q-ID`, one line of context, 2–4 options with trade-offs, your recommendation, and what you will work on while you wait. Never sit idle: continue on unblocked work.
- If a fact in this brief turns out wrong (endpoint moved, dataset gone, limit changed), say so, update the registry and propose the fix.

## 8. Definition of done (every task)

- The code runs from a clean checkout, and `make test` passes. Tests are part of the task: unit tests, plus contract tests at the boundaries.
- Lint and type checks pass (ruff, mypy, and `tsc` for web).
- Data and schema changes ship with an Alembic migration and fixtures.
- Any user-visible change has been checked in the browser (screenshot or recording), with light and dark themes and a 1280 px viewport.
- Docs are updated: `STATUS.md`, the relevant source card or model card, and an ADR if an architectural choice was made.
- Nothing fabricated. Unknown numbers are labelled as estimates and show their source.

## 9. Session protocol

- **Start:** read `docs/STATUS.md` and the brief files for your task, then restate the goal in 3–5 lines.
- **Work:** use small vertical slices with frequent commits, Conventional Commit messages and requirement IDs.
- **End:** update `docs/STATUS.md` (done, in progress, next, blockers, questions waiting on the user).
