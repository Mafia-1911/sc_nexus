# C6 · Tariff & Trade-Policy Monitor: analytical implementation plan (proposal)

**TL;DR.** Watch official tariff schedules and trade-policy notices for the markets Bangladesh
ships to, detect changes automatically, and show them as (1) a **tariff matrix** of products ×
markets × origins, (2) a **change feed** with the legal citation, and (3) the **landed-duty
exposure** of open orders, with a **LDC-graduation scenario** and a **rules-of-origin check** from
the BOM. Tariffs are rules, not predictions, so the core is lookup + diff, not ML; the NLP part
(C2 reading tariff announcements) and the Nexus recommendations are where the "agent" lives.
Four free sources were probed on 2026-11-18 and work (§3). Status: **backend built 2026-11-18** (Q-18/Q-21 = defaults; ADR-021; as built:
`docs/tariffs/BACKEND.md`; feeds and gaps: `docs/tariffs/LIVE_FEEDS.md`). UI not built yet.

## 1. Job to be done

| Persona (01-product) | Question | Answer on screen |
|---|---|---|
| Garment exporter (RMG) | "What duty does my cotton T-shirt pay in the US, EU and UK, and how does that compare with Vietnam, Cambodia, India and China?" | Matrix cell + rate stack (base + surcharge − preference) per market and origin |
| Exporter, planning | "What changed this week, and which of my orders does it hit?" | Change feed; orders re-priced; US$ exposure |
| Exporter, strategy | "What happens to my duty bill when Bangladesh leaves LDC status?" | Graduation scenario: EBA/DCTS-Comprehensive → standard GSP/DCTS-Standard/MFN, with the origin check |
| Pharma importer | "What does Bangladesh charge on the APIs and packaging I import?" | Same matrix, reporter = Bangladesh, partner = China/India (WITS) |
| Logistics planner | "A surcharge starts on date D for goods *loaded* after D. Will my shipment make it?" | P(loaded before D) from Nexus door ETA / C4 (§6.4) |

## 2. Scope

- **Must:** US, EU, UK schedules for the industry-pack HS6 codes (garments + pharma, ≈ 25 codes);
  change detection on the US HTS and UK tariff by snapshot diff; Federal Register feed; tariff
  matrix + change feed + product drill-down page; exposure of open (synthetic) orders; every
  rate cites source, retrieval date and legal reference; LIVE/REPLAY badges.
- **Should:** LDC-graduation scenario; rules-of-origin check from the BOM; competitor-origin
  comparison; C2 extraction of tariff numbers from news; Nexus "ship before the effective date"
  recommendation.
- **Stretch:** Canada and Japan; EU TARIC files; WTO API (free key); history back to 2018 from
  WITS; an email/brief line "tariff changes today".
- **Not:** legal advice, quota (TRQ) accounting, anti-dumping case tracking, HS classification of
  free-text product descriptions.

## 3. Data sources (probed 2026-11-18; raw samples in `data/samples/DS-TRADE-0[4-7]`)

IDs are proposed; they go into `config/sources.yaml` and get cards in `docs/data-sources/` when
the user approves.

| Proposed ID | Source | Probe result | What it gives | Cadence / limits | Licence |
|---|---|---|---|---|---|
| DS-TRADE-04 | **World Bank WITS (TRAINS) SDMX API**, no key | 200; `reporter/840/partner/000/product/610910/year/2022` → MFN **16.5 %**; EU (918) → **12 %**; BD (050) raw cotton 520100 → **0 %**. EU←BD partner query → 404 (preferential rates not returned for that query) | MFN and (where reported) preferential averages by HS6, any reporter; history | Annual, 1–3 years behind | World Bank terms; TRAINS is UNCTAD data *(verify licence before use, rule 9)* |
| DS-TRADE-05 | **USITC HTS REST** (`hts.usitc.gov/reststop/search`), no key | 200; 6109.10.00 general **16.5 %**, special list (no BD), column 2 90 %. Search "Bangladesh" returns five Chapter 99 lines: 9903.01.66 **+37 %** (from 9 Apr 2025, *terminated*, 90 FR 37963), 9903.02.05 **+20 %** (7 Aug → 5 Oct 2025), 9903.05.26 **+10 %** (U.S. note 52, current at probe time), exemptions 9903.06.12/.13 (note 52 (j)(9), text not read yet) | The live US schedule including country surcharges and in-transit clauses | Updated with each HTS revision; be polite (≥ 2 s) | US government work, public domain |
| DS-TRADE-06 | **Federal Register API** (`federalregister.gov/api/v1`), no key | 200; USTR tariff documents, newest 2026-11-18 | Official notices that announce changes (effective dates, document links) | Daily | Public domain |
| DS-TRADE-07 | **UK Trade Tariff API v2** (`trade-tariff.service.gov.uk/api/v2/commodities/{code}`), no key | 200; 6109100010 third-country duty **12 %**; DCTS Standard **9.6 %**; DCTS Comprehensive **0 %** (**Bangladesh is a member**) | Measures by geographical area, with start dates | Daily | Open Government Licence *(verify)* |
| (later) DS-TRADE-08 | EU TARIC | `measures.jsp` HTML returned, rates not in static HTML | — | — | Probe the TARIC data files or Access2Markets next |
| (later) DS-TRADE-09 | WTO Timeseries API | 401 without key (free registration) | MFN/bound tariffs, many reporters | — | Needs a key (D-07 allows; user sign-up) |
| existing DS-TRADE-01/02 | Comtrade, BACI | Bangladesh self-reports nothing (sample has 0 rows) → use **mirror** flows (US/EU/UK imports from BD) | Trade value per HS6 × market to weight exposure | Annual | as registered |

Rules for the sources: cache everything, raw archive per poll (existing connector framework),
User-Agent `Cportal/0.1.0 (...)`, sequential calls ≥ 2 s apart.

## 4. Domain model (new tables; one Alembic migration; all with the `Lineage` mixin)

| Table | Key columns | Notes |
|---|---|---|
| `tariff_line` | `market_iso3`, `hs_code` (6–10 digits), `nomenclature` (HS2022/national), `regime` (MFN, GSP, EBA, DCTS-*, FTA, SURCHARGE, EXEMPTION), `origin_iso3` or `origin_group`, `rate_ad_valorem_pct`, `rate_specific` + `unit`, `rate_text` (verbatim), `valid_from`, `valid_to`, `legal_ref`, `source_url`, `snapshot_id` | Verbatim text kept so nothing is lost when a rate is compound or specific |
| `tariff_snapshot` | `source_id`, `market_iso3`, `retrieved_at`, `content_hash`, `raw_ref` | One per poll; the diff runs between consecutive snapshots |
| `tariff_change` | `market_iso3`, `hs_code`, `regime`, `origin`, `old_rate_text`, `new_rate_text`, `delta_pp`, `effective_from`, `detected_at`, `published_at`, `document_url`, `kind` (new/removed/changed) | Emits outbox `tariff.changed` |
| `trade_preference` | `market_iso3`, `scheme`, `member_iso3`, `valid_from`, `valid_to`, `origin_rule_ref`, `notes` | e.g. UK DCTS Comprehensive ∋ BGD; EU EBA ∋ BGD |
| `origin_rule` (Should) | `market`, `scheme`, `hs_chapter`, `rule` (e.g. "single transformation" / "double transformation"), `legal_ref` | Small curated YAML → table, each row with a citation |

`trade_flow` (exists) supplies mirror trade values for weighting. Orders, products and BOMs come
from the synthetic world (`industry_packs/*.yaml` already carry real HS6 codes).

**Truth labels:** tariff rates are real (LIVE/REPLAY badge); orders are synthetic (SYNTHETIC
badge). The exposure card shows both badges and never names a real firm (rule 3).

## 5. Pipeline (`packages/c6_tariffs`, imports only `packages/core`; ADR-021 if Q-18 = a)

```
connectors (DS-TRADE-04..07) ──► raw archive ──► parse ──► tariff_snapshot + tariff_line
                                                           │
                                              diff vs previous snapshot
                                                           ▼
                                   tariff_change ──► outbox "tariff.changed"
                                                           │
             ┌─────────────────────────────────────────────┼─────────────────────────┐
             ▼                                             ▼                         ▼
   effective-rate engine (§6.1)                C2 links news/FR docs (§6.3)   Nexus recs (§6.4)
             ▼
   exposure per order / product / market (§6.2) ──► API ──► Tariff Monitor page
```

Worker jobs: `c6:poll_us` (daily HTS + Federal Register), `c6:poll_uk` (daily), `c6:wits`
(monthly), `c6:refresh` (on `tariff.changed`: recompute exposure, then `nexus:refresh`).

## 6. Analytics

### 6.1 Effective rate (deterministic, unit-tested)

For market *m*, HS code *h*, origin *o*, date *t*:

```
base     = preferential rate if o ∈ scheme members at t and the origin rule passes, else MFN
extra    = Σ surcharges for (m, o, h) valid at t, minus exemptions that apply
effective_pct = base + extra            (ad valorem; specific duties converted with unit value)
```

Precedence and stacking are market-specific (US Chapter 99 adds to the subheading rate, "The duty
provided in the applicable subheading + 10 %"); each rule is a function with a test built from a
probed sample line. Where a rule can't be resolved (compound duty, unread note), the cell shows
"see legal text" with the link, never a guessed number (rule: nothing fabricated).

### 6.2 Exposure

```
duty_usd(order) = Σ_lines qty × unit_value_usd × effective_pct(m, h, BGD, ship_date)
Δduty(change)   = duty after − duty before, over open orders whose arrival ≥ effective_from
market_weight   = mirror trade value (Comtrade/BACI) for the "national" view
```

Shown: US$ exposure by market and product, top orders hit, and the national view (e.g. "a +10 pp
US surcharge on HS 6109 × US$X of 2024 US imports from Bangladesh", with the trade-flow source).

### 6.3 Change detection and NLP (the "agent" part)

1. **Structured diff** (authoritative): consecutive snapshots of each schedule; any changed
   `rate_text`/`valid_*` → `tariff_change`. Planted-change replay test for acceptance.
2. **Federal Register**: new USTR/CBP documents with tariff terms → linked to the change by HTS
   heading numbers found in the text, so the feed shows "why" and "from when".
3. **C2 news**: articles already classed `TRADE_POLICY_SANCTION` get extra fields: markets,
   HS chapters, rate, effective date (rules first, `qwen3:4b` second opinion with grounded spans,
   as ADR-017). A news-only claim is shown as **"announced, not in schedule yet"** until the
   structured diff confirms it: the same evidence-fusion idea Nexus already uses.

### 6.4 Nexus hooks

- **Ship-before-effective-date:** US surcharges exempt goods *loaded* before a cut-off (text in
  9903.01.66 and 9903.02.05). For each open order: P(loaded before cut-off) from the door-ETA
  Monte Carlo and C4 waits; EV = P × Δduty. Becomes a `pull_forward_po`-style recommendation in
  the existing engine (expected value, evidence = the change + the FR document).
- **Market mix:** for a product, rank markets by effective duty and show the gap vs competitor
  origins (Vietnam, Cambodia, India, China) for the same HS code.
- Scenario Studio gets a "tariff" shock type (Should).

### 6.5 LDC-graduation scenario and rules of origin (Should; the highlight)

- Toggle "after LDC graduation": swap BGD's scheme membership per market to its post-transition
  scheme (EU: EBA → standard GSP; UK: DCTS Comprehensive → Standard (9.6 % on 6109100010, probed);
  US: no GSP for apparel → unchanged). Dates and transition periods come from a cited YAML
  *(verify: graduation 24 Nov 2026; EU EBA transition to 2029; UK transition)*.
- **Origin check** from the BOM the world already has: `TSHIRT ← KNIT_FABRIC` (some from
  Shaoxing, China) `← COTTON_YARN`. Under LDC rules garments typically need single transformation
  (fabric → garment); under standard GSP, double (yarn → fabric → garment) *(verify the exact EU
  and UK rules and cite them)*. The check walks the C1 graph: an order whose fabric is imported
  fails double transformation → loses the preference → pays MFN. Show "orders that lose the
  preference" and the duty they would pay. This connects tariffs to the supplier graph, which is
  the part no generic tariff site shows.

## 7. API (all reads < 300 ms p95; precomputed)

| Method | Path | Returns |
|---|---|---|
| GET | `/tariffs/matrix?hs=&markets=&origins=&date=&scenario=` | cells: effective %, stack parts, badge, source refs |
| GET | `/tariffs/lines/{market}/{hs}` | lines, history (step series), legal refs |
| GET | `/tariffs/changes?since=&market=` | change feed with documents |
| GET | `/tariffs/exposure?scope=&scenario=` | US$ by market, product, order; deltas from changes |
| GET | `/tariffs/origin-check?order_id=` | pass/fail per scheme with the BOM path |

## 8. UI ("Tariff Monitor", new nav item between Disruption Radar and Route Planner)

Build with the ui-consistency flow (finding-patterns → planning → implementing → verifying) so
it matches the other pages (glass cards, `DataBadge`, glossary, light and dark, 1280 px).

1. **Header KPIs:** changes in the last 30 days, open-order duty (US$), exposure to the latest
   change, orders losing a preference after graduation.
2. **Change feed** (left): dated cards "US · HS 6109 · Bangladesh · +20 % → +10 %", effective
   date, document link, "announced (news) / in schedule" chip.
3. **Tariff matrix** (centre): rows = products (HS6 + name), columns = markets; cell colour =
   effective rate on a sequential scale (dataviz skill); origin selector (BGD vs competitors) and
   "after graduation" toggle; cell hover = rate stack.
4. **Drill-down drawer:** rate-stack bar (base, surcharge, preference), step chart of the rate
   over time with change markers, legal text excerpts, orders affected, origin check result.
5. **Exposure** (bottom): bars by market, top orders, Nexus actions ("ship before 5 Oct": EV).

## 9. Evaluation and acceptance (proposed C6-ACxx)

| ID | Criterion |
|---|---|
| C6-AC01 | 20 spot-checked lines (≥ 5 per market) match the official page on the check date: 20/20 |
| C6-AC02 | A planted change in a replayed snapshot is detected within one poll and reaches the feed, exposure and Nexus |
| C6-AC03 | Every displayed rate shows source, retrieval date and legal reference; unresolved rules show "see legal text" |
| C6-AC04 | Effective-rate engine: unit tests per stacking rule from probed samples (US Ch. 99 add-on, UK DCTS, MFN) |
| C6-AC05 | Matrix and exposure endpoints < 300 ms p95 |
| C6-AC06 | C2 tariff extraction: precision/recall on ≥ 30 labelled tariff articles, reported honestly, rules vs LLM |
| C6-AC07 | Licences of DS-TRADE-04..07 recorded; NC licences flagged |

There is no model to beat a baseline here (rule 5 applies only to the C2 extraction).

## 10. Slices and estimate (≈ 4–5 working days)

| Day | Slice | Done when |
|---|---|---|
| 1 | Connectors DS-TRADE-05/06/07 + source cards + registry; migration; parse to `tariff_line` | Rows for the ≈ 25 HS codes in US and UK; tests on the samples |
| 2 | Snapshot diff → `tariff_change` + outbox; effective-rate engine + tests; WITS for history/competitors | C6-AC02, AC04 |
| 3 | API + Tariff Monitor page (matrix, feed, drawer), badges, both themes, e2e | Screenshot light/dark at 1280 px |
| 4 | Exposure + Nexus "ship before" recommendation; C2 tariff fields | Hero order shows Δduty and an action |
| 5 | Graduation scenario + origin check; golden-path step; docs, cards, STATUS | C6-AC01 spot check signed off |

Cut line if short: drop C2 extraction (day 4 half) and competitor origins; keep the graduation
scenario (it is the story).

## 11. Risks and guardrails

| Risk | Guardrail |
|---|---|
| Tariff law is complex (compound duties, notes, TRQs) | Keep verbatim text; show "see legal text" instead of a guess; scope to ≈ 25 codes |
| National 8/10-digit vs HS6 | Store the national code; roll up to HS6 only for the matrix, showing the range |
| Stale or lagging data (WITS 1–3 years) | Badge each cell with the source date; prefer live schedules (HTS, UK) |
| Policy facts from memory (graduation dates, origin rules) | Each in a cited YAML row; marked *estimate* until a source is attached |
| Legal reliance | Footer: "Information, not legal or customs advice. Check the official schedule." |
| Real firms | Exposure only on fictional synthetic orders; national view on public trade totals |
| Site load | Daily polls, ≥ 2 s spacing, raw archive, User-Agent |

## 12. Open questions (see the analysis doc §8)

Q-18 package placement, Q-19 order, Q-21 markets. Also needs the user before build: whether to
register for the WTO API key (DS-TRADE-09) and the EU source choice (TARIC files vs curated EBA
table).
