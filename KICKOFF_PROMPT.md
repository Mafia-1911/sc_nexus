# Kickoff prompts

Open `cportal/` as the workspace root, so `AGENTS.md` is picked up. Paste **Prompt 1** as the first message. Use **Prompt 2** to start every later session.

---

## Prompt 1: Session 1 (M0 Recon, stops at gate G0)

> You are starting **Cportal / Supply Chain Nexus**. Read `AGENTS.md`, then `docs/brief/00-INDEX.md`, `01-product.md`, `02-architecture.md`, `03-data-sources.md` and `07-decisions.md`. Read nothing else yet.
>
> This session covers **Milestone M0 (Recon) only**. Don't build any capability.
>
> 1. **Ask me the kickoff questions** marked `ask-at: kickoff` in `07-decisions.md`, in one batched message, each with a recommendation. While you wait, carry on with step 2.
> 2. **Scaffold the minimum repo** needed to probe sources. Follow the layout in `02-architecture.md` §4. Include a uv workspace with `packages/core` and `packages/connectors`, `config/sources.yaml`, `.env.example` listing every key the registry needs, a Makefile, and `docs/STATUS.md` plus `docs/DECISIONS.md` copied from the templates in `07-decisions.md`.
> 3. **Build the probe harness** described in `03-data-sources.md` §3: `uv run probe <DS-ID>` saves the request, raw response and metadata, plus an inferred JSON Schema. Add one connector module per source.
> 4. **Probe every P0 source**, then the P1 sources if time allows. A source that needs a key or registration I haven't provided yet goes in a "needs you" list with the exact sign-up URL and env var name. Then move on. For each source, test the failure modes in §3 without exceeding any documented limit. Start the long-running AIS collector (`DS-AIS-01`) early, so coverage data builds up while you work.
> 5. **Write the outputs:** one card per source in `docs/data-sources/<DS-ID>.md`, plus `docs/data-sources/PROBE_REPORT.md`. The report needs a summary table (status, auth, limits, licence, Bangladesh coverage, freshness, history depth), the surprises, the blockers, and proposed changes to the canonical schema in `04-domain-model.md`, each with the evidence behind it.
> 6. **Stop at G0** and present the report summary, the "needs you" list, the schema changes you propose and your plan for M1. Wait for my go-ahead.

---

## Prompt 2: Later sessions

> Continue **Cportal**. Read `AGENTS.md` and `docs/STATUS.md`. Then read only the brief files the retrieval map lists for **<MILESTONE / TASK, e.g. "M3, C1 thin slice">**. Restate the goal and acceptance criteria (`Cn-ACxx`) in five lines, list any `Q-xx` that still needs my answer, then execute. Stop at the gate or soft gate defined in `06-roadmap.md`. Update `docs/STATUS.md` before you finish.

---

## Prompt 3: Unblock or correct the agent

> Pause. Re-read `AGENTS.md` §4 (hard rules) and §7 (ask, don't assume). Tell me which assumption you made that isn't backed by the brief or `docs/DECISIONS.md`, what evidence you have for it, and the options. Then wait.
