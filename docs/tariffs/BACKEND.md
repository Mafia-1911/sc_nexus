# Tariff Monitor (C6): backend as built, API for the UI, and what is left

**TL;DR.** Built and tested on 2026-11-18: four live connectors and one hand-kept table write
8 tables; C6 marks current measures, detects changes between snapshots, and precomputes the
effective duty for **5 markets × 22 products × 7 origins** (770 cells, ≈ 0.3 s). Six read
endpoints under `/api/v1/tariffs` serve the screen (all < 40 ms median, 300 ms p95 budget
tested). Design: ADR-021. Feeds and gaps: [LIVE_FEEDS.md](LIVE_FEEDS.md).

## 1. Data flow

```
DS-TRADE-05 USITC HTS ─┐
DS-TRADE-07 UK tariff ─┤ parsers (packages/connectors/.../parsers/tariffs.py)
DS-TRADE-04 WITS ──────┤   → nomenclature, measures (versioned), origin groups + members,
DS-TRADE-08 EU table ──┘     one snapshot per fetched part
DS-TRADE-06 Fed. Reg. ──→ trade_policy_notice
            │ loader upsert (worker live refresh, or `make seed` replay)
            ▼
outbox source.ingested ─→ worker c6.refresh (also every 6 h) ─→ cportal_c6.store.refresh:
   1. mark_current      latest snapshot per (source, scope) → is_current
   2. detect_changes    consecutive snapshots → tariff_change (+ outbox tariff.changed)
   3. compute_rates     rates.effective_rate per market × HS6 × origin → tariff_effective_rate
            ▼
apps/api routers/tariffs.py → cportal_c6.service → JSON {data, meta}
```

## 2. How the tables connect (relations across regions and products)

| Join | Lets the UI / Nexus answer |
|---|---|
| `tariff_nomenclature.hs6` = `tariff_measure.hs6` = `product.hs6` = `trade_flow.hs_code` (6) | The same product across markets; which synthetic orders and real trade flows it touches |
| `tariff_nomenclature.parent_code` → `code` | The product tree (heading → HS6 → national 8/10-digit lines) |
| `tariff_measure.origin_group_id` → `tariff_origin_group.id` ← `tariff_origin_member.group_id` | Which countries a preference covers; which schemes a country is in, per market and date |
| `tariff_measure.code = '*'` + `origin_code` = ISO3 | Country-wide surcharges (US Chapter 99) that apply to every product of an origin |
| `tariff_snapshot.measure_ids` ∋ `tariff_measure.id` | What the schedule said at each fetch (history), and what is current |
| `tariff_change.old_measure_id` / `new_measure_id` → `tariff_measure.id` | The exact old and new rule behind a change |
| `trade_policy_notice.countries`, `.hts_refs` | Notices that name an origin or an HTS heading (link to changes and surcharges) |
| `tariff_effective_rate (as_of, market, hs6, origin)` | The matrix cell, with its sources, notes and representative breakdown |

Snapshots carry the parser version (`generator_version`); C6 diffs only snapshots made by the
same version, so improving a parser never shows up as tariff changes (A-133).

Every row has the lineage columns (`source_id`, `data_mode` live/replay, `available_at`, …);
tariffs never carry synthetic rows.

## 3. Engine rules (`packages/c6_tariffs/src/cportal_c6/rates.py`, 20 unit tests)

1. **Base** = most specific MFN for every origin (or column 2 for its group); annual WITS rates
   past their year are used and flagged `is_stale`.
2. **Preference** = lowest resolved rate among the origin's FTAs/schemes valid on the date
   (membership dates respected); relative rules ("MFN − 20 %") computed; partial eligibility
   (US `E*`) listed, not applied. Rules of origin assumed met (note).
3. **Surcharges** add; more than one for the same origin → **unresolved** with an "if they
   all stack" note (US China lines).
4. **Exemptions, quotas, suspensions, trade remedies** are components with a note, never a number.
   A US **product-category exemption** (e.g. 9903.05.89, pharmaceutical applications) on a
   product's chapter makes any surcharge unresolved with the reason (A-133).
5. Specific or compound duties, staged FTA rates, averages over differing lines → unresolved.

## 4. API for the Tariff Monitor screen

All under `/api/v1/tariffs`; envelope `{data, meta}`; `meta.mode` = live | replay | mixed |
none and `meta.sources` = DS-IDs (badge); `meta.note` carries the "not legal advice" line.
Full schema: `docs/api/openapi.json`.

| Endpoint | UI region (plan §8) | Returns |
|---|---|---|
| `GET /overview` | Header KPIs, market chips, feed status panel | markets (live source, last fetch, mode, measures), origins, 22 products, feeds (live / manual / missing + to-do), `changes_30d`, `notices_30d`, `latest_change_at` |
| `GET /matrix?as_of&hs6&market&origin&industry` | Tariff matrix (heatmap) | cells: min/max effective %, base, preference, surcharges, resolved, stale, `note_ids` into a shared `notes` list, sources, mode; `precomputed` false for other dates |
| `GET /products/{hs6}?as_of&market&origin` | Drill-down drawer | per market and origin, each national line: description, effective %, components (role, reference, duty text, %, legal ref, source URL, dates), notes; recent changes |
| `GET /changes?market&origin&hs6&since&limit` | Change feed | old/new duty text and %, delta pp, status change, effective from, detected at, source, mode |
| `GET /notices?kind&country&limit` | Notices list | Federal Register notices: kind, countries, HTS refs, link |
| `GET /origins/{iso3}?as_of` | Country panel ("Bangladesh in each market") | schemes/FTAs per market with dates, country-wide surcharges with status and legal refs |

Measured on the replayed samples (local Postgres, in-process client, 20 calls): matrix median
25 ms (max 34 ms, 204 KB), product 30 ms, overview 18 ms.

## 5. Verification (what the tests prove)

| Test file | Count | Proves |
|---|---|---|
| `packages/connectors/tests/test_tariff_parsers.py` | 58 | Every parser against the real samples: duty text forms, HS tree, US programmes and members, Chapter 99 countries / dates / terminations / exemptions, UK groups and members (BD ∈ 1062), WITS averages, Federal Register kinds and countries, EU table, content-versioned ids, live HTTP query strings |
| `packages/connectors/tests/test_replay_contract.py` | +15 cases | The five new sources replay into their declared records with lineage, deterministically |
| `packages/c6_tariffs/tests/test_rates.py`, `test_diff.py` | 20 + 6 | One engine or diff rule per test |
| `tests/test_c6_tariffs_e2e.py` | 21 | Real Postgres: official duties come out (US BD 26.5 %, VN 29 %; UK BD 0 %, CN 12 %; EU BD 0 %, IN 12 %, VN unresolved; China unresolved; US medicaments unresolved by the pharma exemption); a parser upgrade creates no changes; a planted +5 pp change is detected once, re-keys the measure, moves the rate to 31.5 % with a LIVE badge, emits one outbox event, and a second refresh finds nothing new |
| `tests/test_c6_api.py` | 16 | Endpoint contracts, filters, badges, errors (422/404), on-the-fly dates, latency budget |
| `apps/worker/tests/test_c6_worker.py` | 2 | A tariff `source.ingested` event refreshes the matrix through the dispatcher; the job is scheduled |

Mutation checks (a deliberate bug, then the test run) were done for the country span rule, the
entered-before date, the membership end date and the unresolved-preference rule: each was caught.

## 6. Remaining backend work, in order (with the UI in mind)

| # | Step | Why (UI need) | Size |
|---|---|---|---|
| 1 | **Graduation scenario**: `config/tariffs/graduation.yaml` (cited scheme transitions per market: EU EBA → GSP, UK DCTS Comprehensive → Standard) applied by the engine for an `as_of` after the transition; `GET /matrix?scenario=ldc_graduation` | The "after LDC graduation" toggle | S |
| 2 | **Exposure**: duty on open (synthetic) orders by market using `customer_order` × product HS6 × buyer gateway country; Δduty per change; national view from `trade_flow` mirror values | Exposure strip and KPI "duty on open orders" | M |
| 3 | **Rules-of-origin check** from the BOM (C1 graph via `cportal_c1.service`, called from Nexus, not C6): imported fabric → fails double transformation → loses the preference | "Orders losing the preference" | M |
| 4 | **Nexus recommendation** "ship before the cut-off" using `conditions.loaded_before` and the door-ETA Monte Carlo | Actions card | S–M |
| 5 | **C2 link**: TRADE_POLICY_SANCTION events get market / HS / rate fields; shown "announced, not in schedule" until a `tariff_change` confirms | "Announced" chip in the change feed | M |
| 6 | **Section 301/232 ranges** (9903.80–9903.91) with product lists | Correct China numbers | M |
| 7 | **Daily brief line** for new tariff changes (Control Tower) | Cross-page hook | XS |
| 8 | Missing feeds (LIVE_FEEDS.md §2), EU TARIC first | Live EU numbers | M each |

## 7. Commands

```bash
uv run c6 refresh                                   # current flags, changes, matrix for today
uv run c6 rate 610910 --market GBR --origin BGD     # one product's breakdown as JSON
uv run c6 changes                                   # latest detected changes
uv run ingest --replay DS-TRADE-05                  # load the committed samples for one source
```
