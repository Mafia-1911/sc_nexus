# Tariff Monitor (C6): live feeds, gaps and to-do

**TL;DR.** The US and UK schedules are live and complete for the 22 watched HS6 codes. US
trade notices are live. The EU, Japan and Canada have **MFN rates only** (WITS, 2023, flagged
stale), and the EU's preferences come from a **hand-kept table**. Seven feeds are still missing
(table 2). Machine-readable status lives in `config/tariffs/feeds.yaml` and is served by
`GET /api/v1/tariffs/overview`, so the UI can show it. ADR-021 has the design.

Probed 2026-11-18 from this environment, without keys. Raw samples: `data/samples/DS-TRADE-04…07`.

## 1. Feeds in use

| DS-ID | Source | Market | What it gives | Mode / cadence | Notes |
|---|---|---|---|---|---|
| DS-TRADE-05 | USITC HTS REST (`exportList`) | USA | General, special (FTA/GSP programmes) and column-2 rates per 8-digit line; Chapter 99 country surcharges and exemptions (9903.01–9903.07) | live, daily (22 calls) | Public domain. Programme membership from `config/tariffs/us_programs.yaml` (hand-kept, HTS General Note 3) |
| DS-TRADE-06 | Federal Register API | USA | Official notices from USTR, ITA, ITC, CBP, the President's office, BIS: kind, countries named, HTS numbers | live, every 6 h | Mostly AD/CVD cases; tariff modifications are a few per month |
| DS-TRADE-07 | UK Trade Tariff API v2 | GBR | Every import measure per 10-digit commodity, origin groups with member countries (DCTS, FTAs), start/end dates, legal acts | live, daily (≈ 190 calls, ≈ 3 min) | OGL (verify). 169 commodities for the watched codes |
| DS-TRADE-04 | WITS TRAINS SDMX | EUN, USA, GBR, JPN, CAN | Reported MFN simple averages by HS6, with the number of national lines and min/max | live, weekly | 1–3 years late (2023 newest). Used as the base only where no live schedule exists |
| DS-TRADE-08 | EU preferences (manual) | EUN | EBA (Bangladesh, Cambodia), GSP+ (Pakistan, Sri Lanka), standard GSP rule (−20 % on chapters 61–63, no members), EVFTA (Vietnam, unresolved) | manual | `config/tariffs/eu_preferences.yaml`; every row `verify: true` |

## 2. Missing feeds (to-do, in priority order)

| # | Feed | Why it matters | What blocks it | Next step |
|---|---|---|---|---|
| 1 | **EU TARIC (current applied rates and preferences)** | The EU is Bangladesh's largest garment market; today its numbers are the 2023 WITS average plus a hand-kept table | TARIC's `measures.jsp` renders rates in the browser (no rates in the static HTML); Access2Markets has no public API | Probe the TARIC data-dissemination XML files (monthly) and EU "TARIC3" downloads; if usable, write DS-TRADE-09 into the same tables and retire DS-TRADE-08's measures |
| 2 | **EU Official Journal acts** (duty and GSP changes) | Change detection for the EU, like the Federal Register for the US | Not probed | Probe the EUR-Lex search/SPARQL endpoint for regulations amending the CN or GSP |
| 3 | **UK notices** (tariff notices, trade remedies) | The UK has live rates but no "why" feed | Not probed | Probe the GOV.UK search API (`/api/search.json`) for trade-remedy and tariff notices |
| 4 | **Japan applied tariff and GSP/LDC preferences** | Japan is a growing RMG market; Bangladesh has LDC duty-free access | Japan Customs publishes per-chapter HTML/PDF; no API | Parse the per-chapter HTML for the watched headings, or keep WITS MFN plus a hand-kept LDC table |
| 5 | **Canada customs tariff and LDCT** | Canada is a top-10 RMG market | CBSA publishes PDF/HTML per chapter; no API | Same approach as Japan |
| 6 | **Bangladesh import duties (NBR)** | Pharma APIs and garment inputs are imported; duty changes hit costs | NBR publishes the budget-year schedule as PDF; `customs.gov.bd` failed TLS verification from this network | Probe NBR's PDF schedule (pdfplumber is already a dependency) |
| 7 | **WTO Timeseries API** | Bound vs applied rates for any reporter; cross-check for WITS | Needs a free API key (401 without one) | User sign-up (allowed by D-07); add the key to `.env` |

## 3. Known limits of the feeds in use (to-do in C6, not feeds)

- **US note-52 exemptions** (9903.06.12/.13 for Bangladesh, (j)(9)): the conditions are in
  U.S. note 52, which is not parsed. The matrix shows them as "possible exemption".
- **US product-category exemptions** (9903.05.89 pharmaceutical applications, 9903.05.90
  Section 232 goods, …): their HS lists are in the U.S. notes. A cited keyword → chapter map
  (`config/tariffs/us_exemption_categories.yaml`, estimate) makes surcharges on pharma
  (chapters 29–30) and metals (72–76) **unresolved** with the reason. Next: parse the notes'
  HS lists (they are in the HTS General Notes / chapter 99 notes PDF).
- **US China lines:** 9903.01.20, 9903.01.24, 9903.01.63 and 9903.05.31 are all in force per
  their text; whether they stack is in the notes. China's US cells are unresolved, with the
  "if they all stack" figure.
- **US Section 301 / 232 lists** (9903.88.xx, 9903.81.xx) are outside the fetched range: China
  goods on the 301 lists pay more than the matrix shows. Next: fetch 9903.80–9903.91 and parse
  the product lists.
- **Rules of origin** are assumed met. The plan's BOM-based origin check (Bangladesh's
  imported fabric vs EBA / DCTS rules) is the next C6 slice.
- **LDC graduation scenario:** the EU table already ends Bangladesh's EBA on 2029-11-24
  (estimate: graduation 24 Nov 2026 + 3 years). The UK data has no end date for DCTS
  membership, so the UK cell does not change yet. A cited `config/tariffs/graduation.yaml`
  (scheme transitions per market) is the next step.
- **History** starts with our first snapshot; the HTS and UK APIs serve the current schedule
  only. Change detection works from the second daily fetch onward.

## 4. How to add a feed

1. Probe it (`uv run probe DS-…`), save samples, write the card entry in
   `docs/data-sources/cards.yaml` and the registry row in `config/sources.yaml`.
2. Parse into the existing records (`TariffNomenclatureRecord`, `TariffMeasureRecord`,
   `TariffOriginGroupRecord`, `TariffOriginMemberRecord`, `TariffSnapshotRecord`) with one
   snapshot per fetched part; parser tests on the real sample.
3. If it is the market's main schedule, set `markets.<code>.live` in
   `config/tariffs/watchlist.yaml`; add its DS-ID to `TARIFF_SOURCES` in
   `apps/worker/src/cportal_worker/c6.py` and the outbox list.
4. Move its row in `config/tariffs/feeds.yaml` from `missing` to `live`.
