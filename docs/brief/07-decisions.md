# 07 · Decisions, open questions, templates

**TL;DR.** `D-xx` are settled; don't re-ask them. `Q-xx` are open. Each has a **default** you may use for reversible work while waiting, and an **ask-at** marker saying when you must raise it. Batch questions, at most four per message, each with a recommendation (`AGENTS.md` §7). Log every answer and every assumption in `docs/DECISIONS.md`.

## 1. Decisions made (by the user, 2026-10-26)

| ID | Decision | Rationale / implication |
|---|---|---|
| D-01 | Bangladesh first (Chattogram, Mongla, Payra → Dhaka-area garment and pharma clusters; lanes via Colombo/Singapore) | Probes, seed graph, routing corridor and demo all centre on Bangladesh. Other countries' open AIS is allowed for training |
| D-02 | Hackathon horizon (weeks); polished demo first | Pretrained and zero-shot models first; thin slices; cut lines in `06-roadmap.md` §3 |
| D-03 | Train in free Colab/Kaggle notebooks; app runs CPU-only inference | Notebook flow in `02-architecture.md` §7; CPU budgets in §11 |
| D-04 | The C4 primary target is **vessel dwell** (anchorage wait + berth time) | Container dwell later, as a derived estimate feeding C3 |
| D-05 | Stack: FastAPI, SQLAlchemy 2, Pydantic v2, psycopg 3, Postgres (PostGIS, pgvector), Next.js, Tailwind v4, docker-compose | Mirrors the user's existing projects |
| D-06 | Modular monolith; no extra services without an ADR | — |
| D-07 | No paid APIs or data; free registrations are OK | Paid list in `03-data-sources.md` §2.10 |
| D-08 | Probe real APIs first, then design schemas, then synthetic data with the same schema, then swap per source | — |
| D-09 | Build order: backbone, C1, C2, C3, C4, C5, Nexus | — |
| D-10 | Theme: calm and oceanic; clean and modern | Tokens in `05-ui-design.md` |

## 2. Open questions

| ID | ask-at | Question | Options | Default (use while waiting) |
|---|---|---|---|---|
| Q-01 | **kickoff** | What is the deadline, demo format (live or recorded), judging criteria and team size? | — | 4 weeks; live demo plus a backup video; solo builder plus agent |
| Q-02 | **kickoff** | Must the demo be hosted online, or is a local laptop fine? | Local only · online (Neon + container host + Vercel) | Local, replay mode |
| Q-03 | **kickoff** | What is the LLM policy for news extraction and briefs? | (a) Local only: GLiNER2 + a small local LLM (e.g. Qwen3.5-4B / Qwen3-4B-Instruct or Gemma 4 E4B; verify current best) via llama.cpp/Ollama, with grammar-constrained JSON. (b) Also allow a **free-tier** hosted LLM for backfill and briefs. (c) Paid API (conflicts with D-07) | (a), with a bigger open model run in a Kaggle notebook for silver labels |
| Q-04 | **kickoff** | Which free accounts will the user create, and when? | aisstream, GFW, Copernicus CDSE, UN Comtrade, openFDA key, ReliefWeb appname, Kaggle, Open Supply Hub, ORS, (ACLED) | The agent lists the exact URLs and env vars; uses replay or synthetic until keys arrive |
| Q-05 | **kickoff** | Real company names in the graph? | (a) Fictional firms only, at real infrastructure. (b) Real facilities from OSH with **only sourced attributes**, plus fictional firms for anything simulated | (a) for the demo; (b) as an optional "real map" layer |
| Q-06 | **kickoff** | Are non-commercial licences (GFW CC BY-NC, MVTec CC BY-NC-SA, ACLED) acceptable for the hackathon? | Yes, flagged · no | Yes, flagged in cards and UI |
| Q-07 | **kickoff** | Branding in the UI? | "Supply Chain Nexus" · "Cportal" · both | "Supply Chain Nexus" in the UI; Cportal as the repo codename |
| Q-08 | **kickoff** | Which industry is the hero of the demo? | Garments hero, pharma variant · pharma hero · equal | Garments hero; pharma variant at the end |
| Q-09 | kickoff | Hero disruption scenario? | Cyclone · strike/blockade · customs outage · Red Sea diversion · rail shortage | Cyclone + supplier delay (combined) |
| Q-10 | M4 start | Bangla-language news in scope? | English editions only · plus Bangla with translation | English editions first; Bangla as stretch |
| Q-11 | M4 start | How much time can a human spend on annotation (C2 gold set, C5 checks)? | ~2 h · ~5 h · none | ~3 h (300 articles, pre-annotated) |
| Q-12 | M3 start | GNN in hackathon scope? | Analytics + simulation only · plus GNN risk scoring · plus GNN surrogate/link prediction | Analytics + simulation, then GNN risk scoring as stretch with an honest comparison |
| Q-13 | M5 start | Corridor extent and modes? | CGP → Dhaka, Gazipur, Savar, Narayanganj by road + rail (Kamalapur) + barge (Pangaon) · also Mongla/Payra → Dhaka via Padma Bridge | Both; Mongla gives the "alternative port" story |
| Q-14 | M5 start | RL in scope? | Skip · experiment behind a flag, benchmarked against OR | Experiment only if M5 finishes early |
| Q-15 | M6 start | Satellite depth? | GFW SAR counts + scene thumbnails · plus our own S1 ship detector | Counts + thumbnails |
| Q-16 | M7 start | Demo product categories? | Fabric + finished garment · tablets/capsules/blisters | Fabric (stain/hole) + tablets/capsules |
| Q-17 | M8 start | Publish an MCP server or copilot ("Ask Nexus")? | Skip · read-only copilot in the UI · plus MCP server | Read-only copilot if time allows |

## 3. Templates

### `docs/adr/ADR-nnn-title.md`

```markdown
# ADR-nnn: <title>
Status: proposed | accepted | superseded by ADR-mmm   Date: YYYY-MM-DD
Context: <forces, constraints, evidence (link probe report / benchmarks)>
Decision: <what we do>
Alternatives considered: <option → why not>
Consequences: <+ / − ; what becomes easier/harder; revisit trigger>
```

### `docs/STATUS.md`

```markdown
# STATUS (updated YYYY-MM-DD HH:MM BST by <agent>)
Milestone: Mx (gate Gx due <date>)
Done (this session): - …
In progress: - …
Next (ordered): 1. … 2. …
Blockers: - … (owner)
Waiting on user: Q-xx …
Data modes: DS-AIS-01=live, DS-PORT-01=replay, …
Model versions active: c4=lgbm-0.2.0, …
Demo health: golden path ✅/❌ (last run …)
```

### `docs/DECISIONS.md`

```markdown
| Date | ID | Decision / assumption | Why | Reversible? | Asked user? |
|------|----|------------------------|-----|-------------|-------------|
| YYYY-MM-DD | Q-03 | Local LLM (Qwen3-4B, Q4_K_M) | user answer | yes | yes |
| YYYY-MM-DD | A-001 | Anchorage polygon from OSM seamarks + DBSCAN | no official polygon found | yes | no (default) |
```
