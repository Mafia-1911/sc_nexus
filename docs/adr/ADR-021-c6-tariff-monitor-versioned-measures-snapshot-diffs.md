# ADR-021: C6 tariff monitor as its own capability package, with versioned measures, snapshot diffs and a precomputed rate matrix

Status: accepted   Date: 2026-11-18   Deciders: user (Q-18 → default accepted 2026-11-18)

**Context:** The user asked for a Tariff Monitor screen: watch tariff changes online and compare
tariffs across regions and products (proposal `docs/proposals/C6-tariff-monitor-plan.md`).
Probes on 2026-11-18 found four free sources without keys (WITS, USITC HTS, Federal Register,
UK Trade Tariff) and no machine-readable EU source. Schedules are legal texts: rates can be
specific or compound, preferences depend on origin groups whose membership changes, US country
surcharges are written as prose with conditions, and the same rule can change in place. The
app is CPU-only with a 300 ms read budget (rule 7) and pipelines must stay independent (rule 6).

**Decision:**
- **Package `packages/c6_tariffs`** (`cportal_c6`), importing only core, added to every
  import-linter contract for capabilities. Connectors DS-TRADE-04…08 live in
  `packages/connectors` like every other source; the API calls `cportal_c6.service`.
- **Eight tables** (one migration): `tariff_nomenclature` (product tree per market, `hs6` joins
  markets, industry packs and `trade_flow`), `tariff_measure`, `tariff_origin_group`,
  `tariff_origin_member`, `tariff_snapshot`, `tariff_change`, `trade_policy_notice`,
  `tariff_effective_rate`. EU is market `EUN` (the WITS code).
- **Versioned measures:** a measure's id hashes its content, so a changed rate is a new row and
  the old one stays as history. Product scope `code = "*"` means "all goods of this origin"
  (US Chapter 99). The verbatim duty text is always kept; anything that is not one ad valorem
  percentage is `is_resolved = false` and never turned into a number.
- **Snapshots and diffs:** each fetched schedule part (a US heading, the Chapter 99 range, a UK
  commodity, a WITS market-year, the EU table) writes a `tariff_snapshot` listing its measure
  ids. C6 marks the latest snapshot's measures current and diffs consecutive snapshots by
  natural key (market, code, kind, origin, reference) into `tariff_change` rows with
  deterministic ids, then emits `tariff.changed` on the outbox.
- **Effective rate engine** (pure, `rates.py`): base MFN (or column 2) → best preference for the
  origin's groups on the date (rules of origin assumed met, said in the notes) → plus country
  surcharges; exemptions, quotas, suspensions and trade remedies are listed, not applied.
  Several surcharges for one origin make the result unresolved (stacking is not stated in the
  lines), with the "if they all stack" figure in a note. Annual WITS rates past their year are
  used and flagged stale.
- **Precomputed matrix:** the worker writes `tariff_effective_rate` for today (markets × HS6 ×
  origins, 770 cells in ≈ 0.3 s) after each tariff ingest and every 6 h; other dates are
  computed per request, never written by one.
- **EU by hand:** `config/tariffs/eu_preferences.yaml` (DS-TRADE-08, status manual), every row
  cited and marked `verify: true`; EU MFN from WITS.

**Alternatives considered:** inside `nexus` (mixes a data capability into the fusion layer and
breaks the "capabilities feed Nexus" direction); connectors + API only (no place for the
engine, the diff or the worker job); one mutable row per rule with an audit log (loses the
exact old text and makes "what did the schedule say on date D" a reconstruction); computing
the matrix per request (p95 risk under load: measured 277 ms max before slimming);
scraping TARIC's browser-rendered page (fragile, ToS unclear); a paid tariff API (D-07).

**Consequences:** + every rate traces to a source line, a legal reference and a snapshot; a
change is detected the first time a schedule differs, idempotently; new markets are new
connectors writing the same tables. − Rules of origin are assumed met; US note-52 exemptions
and China's stacked IEEPA lines need a person to read the notes; EU, Japan and Canada current
rates are not live (docs/tariffs/LIVE_FEEDS.md); history starts with our first snapshot.
