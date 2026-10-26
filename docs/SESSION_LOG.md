# Session log

One entry per working session with a coding agent: what was asked, what was done, what was
decided, and where the evidence lives. `docs/STATUS.md` is the live snapshot; this file is the
history. Raw agent transcripts are not committed (A-029).

## Session 1 · 2026-10-26 · Claude Code (Opus 5.5) · M0 Recon → G0

**Asked:** the kickoff prompt (`KICKOFF_PROMPT.md`): read the brief, ask the kickoff questions,
scaffold the minimum repo, build the probe harness, probe every P0 then P1 source, start the AIS
collector, write source cards and `PROBE_REPORT.md`, stop at G0. Mid-session the user added two
standing rules: build on synthetic data with the same schema when a real source fails (U-01), and
never retry a failing API, timeout or search more than twice (U-02, "two strikes").

**Done:**
- uv workspace (`packages/core`, `packages/connectors`), Makefile, `.env.example`, registry
  (`config/sources.yaml`), feeds and areas config.
- Probe harness: `uv run probe <DS-ID>` saves request, raw response, metadata, inferred JSON
  Schema and field profiles; redacts secrets; rate-limits per source; cards are generated.
- 47 sources probed (24 P0, 22 P1, plus NASA Earthdata): 32 verified, 8 needed a sign-up or a
  human step, 7 blocked. 47 cards and `docs/data-sources/PROBE_REPORT.md`.
- AIS: the aisstream collector ran for over an hour and received **zero** Bangladesh messages, so a
  synthetic twin in aisstream's exact frame format was built (MID 999 MMSIs, "SYN" names),
  calibrated to PortWatch and Global Fishing Watch, with a contract test against real frames.
- 37 tests; ruff and mypy clean. Commits `52f2a8e` (code) and `1a64f09` (docs) on `m0-recon`.

**Key findings:** GFW is the real vessel-level source for Chattogram (1,897 port visits in 90
days; port time p50 83 h, p90 276 h; 98 % of cargo visits never reach a dock). GDELT DOC is
rate-blocked from this network (raw files work). 20 brief facts were wrong and were corrected
(e.g. Payra is BDPAY, UN/LOCODE moved host, MVTec links dead, CPPI is non-commercial).

**Ended at:** G0, waiting for the user's answers.

## Session 2 · 2026-10-26 · Claude Code (Opus 5.5) · G0 answers → M1 start

**Asked:** the user answered the kickoff questions (no fixed deadline; local laptop first, Vercel
later; local LLM; real Bangladeshi company names as display names only; garments hero, pharma
variant; brand name as a variable; repo name Cportal), added ReliefWeb, HeiGIT (ORS), Kaggle and
NASA FIRMS keys, downloaded a CPA berthing report, installed Docker, approved everything else, and
asked for a status write-up and a push to `github.com/Mafia-1911/sc_nexus`.

**Done:**
- Answers and assumptions logged (`docs/DECISIONS.md`: G0, Q-01…Q-09, A-023…A-029).
- New keys probed and verified: ReliefWeb, OpenRouteService, Kaggle (MVTec AD mirror), NASA
  FIRMS (new proposed source DS-WX-05). CPA berthing PDF registered as DS-PORT-07 (`manual`).
- Settings gained aliases for the new `.env` names plus the brand, name-pack, database and LLM
  settings. A user-level Postgres 16 + PostGIS + pgvector was installed for M1 (A-023).
- Docker found installed but its socket is not accessible (user not in the `docker` group).
- Cards, PROBE_REPORT tables and STATUS refreshed; history merged with the GitHub repo's initial
  commit and pushed.

**Open:** the Q-05 guardrail confirmation (real names never carry adverse synthetic attributes by
default); Docker group membership; Copernicus login.

**Next:** M1 as listed in `docs/STATUS.md`.
