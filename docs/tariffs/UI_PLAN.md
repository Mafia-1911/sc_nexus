---
topic: Tariff Monitor UI (C6) — new page, tariff cards on existing maps, cross-page hooks
reference: apps/web/components/radar/workbench.tsx (Disruption Radar)
written: 2026-11-18
status: plan — waiting for the user's yes (§9) before any UI code
---

# Tariff Monitor (C6): UI plan

**TL;DR.** One new page, **Tariff Monitor** (`/tariffs`), built the way the Disruption Radar is
built: a thin server page, one client workbench, filter chips, a list card beside a visual
card, and an inline detail card below. Tariffs then appear where a border is actually crossed
on the existing screens: a **"Duty at the border" card on the Route Planner map**, a **tariff
card in the Supplier Network node drawer** (buyers abroad and overseas suppliers), a
**"Tariff check" card on trade-policy events** in the Disruption Radar, and **one line in the
Control Tower brief**. The design was checked against the live data (§2): about half of the
US cells have no single number, so "no number, and why" is a first-class state, not an error.
Seven tasks, with one checklist each (§8). Five questions wait on you (§9).

Process: ui-consistency `finding-patterns` → `planning` (this file). After your yes:
`implementing`, then an independent `verifying` check per page, then the project's own checks
(e2e, axe, screenshots in light and dark at 1280 px). The plugin normally keeps plans outside
the repository; this one is here because you asked for a document (and AGENTS.md wants docs in
`docs/`).

---

## 0. Your question: is tariff news captured live?

**Yes, generic tariff news is captured live today, but it is not connected to the tariff
tables.** Verified on 2026-11-18:

| What | Live? | What it gives | Gap |
|---|---|---|---|
| **Official schedules** (USITC HTS, UK Trade Tariff, WITS, EU table) | yes (C6) | The rates themselves; changes found by comparing snapshots | Only *after* a change is in the schedule |
| **Official notices** (Federal Register) | yes (C6, every 6 h) | US notices: kind, countries, HTS numbers, link | US only; UK and EU notice feeds missing (LIVE_FEEDS.md §2) |
| **News** (C2: RSS, e.g. Daily Star business, The Loadstar; GDELT GKG for Bangladesh) | yes (C2, every 15 min) | Articles with tariff words become `TRADE_POLICY_SANCTION` events on the Disruption Radar, with place and industry | No market, rate, product or effective date extracted; not linked to `tariff_change`; nothing on the Tariff Monitor |

Evidence: the committed Daily Star sample (DS-NEWS-03) has an article whose text reads *"The
United States' decision to apply a zero additional tariff rate to specified specialty
pharmaceutical products…"*. Run through C2's extractor it becomes `TRADE_POLICY_SANCTION`,
place Bangladesh, industry pharma, relevance 0.82. That agrees with the pharma exemption the
schedule shows (9903.05.89).

**Logic gap found on the way (G-9):** C2 treats every trade-policy article as a disruption
with a 90-day prior and may raise buffer-stock recommendations, even when the news is a tariff
*cut* or an exemption. Fix with the C2 link (task T7): extract direction (raise / cut /
exempt), market, rate, product and date; only raises feed the buffer engine; the Tariff
Monitor shows news as **"announced, not in the schedule yet"** until a `tariff_change`
confirms it.

---

## 1. Where tariffs fit in the app (fit check, screen by screen)

A tariff is charged where goods cross a border. Each screen was checked for whether it shows
such a crossing.

| Screen | Its question (05-ui-design §4) | Does it show a border crossing? | Tariff hook | Verdict |
|---|---|---|---|---|
| Control Tower | What needs my attention now? | Ships at Chattogram (real); no cargo HS codes | One brief line: "N tariff changes this week (US 9903.05.26 …)" linking to the Monitor | **Add (T6)**: a line, not a card (the brief already cites rows) |
| Ports & Vessels | When will vessels berth? | Ships, not cargo lines | None: CPA data has no HS codes | **Skip** |
| Supplier Network (geo map) | Where are we fragile? | **Yes:** overseas suppliers (Shaoxing CN, Ahmedabad IN, Memphis US, Kolkata IN) → Bangladesh; Bangladeshi factories → buyers near Rotterdam (EU) and Los Angeles (US) | Node drawer card: duty into the buyer's market for what it buys from Bangladesh, vs competitors; for an overseas supplier, Bangladesh's import duty on its products (**feed missing**: says so) | **Add (T4)** |
| Disruption Radar | What happened, does it affect us? | Trade-policy events | "Tariff check" card in the event drawer: the matching schedule lines, current rate, changes | **Add (T5)** |
| Route Planner (route map) | How do I move this cargo best? | **Partly:** it plans the *domestic* legs only. Port or ICD → cluster is the inland leg of an **import**; cluster → port is the inland leg of an **export** | "Duty at the border" card on the map: for an export, the duty in the chosen market for the chosen product (BGD vs competitors), and any "loaded before" cut-off against the plan's arrival at the port; for an import, Bangladesh's import duty (**feed missing**: says so and links the Monitor) | **Add (T3)**, with a product (and market) picker added to the form |
| Quality Lab | Is this batch OK? | No | None | **Skip** |
| Scenario Studio | What if…? | Scenario shocks | A "tariff change" shock type later (backend first) | **Later** (BACKEND.md §6) |
| Data & Models | Can I trust this? | — | The tariff sources (DS-TRADE-04…08) already appear in the source registry | **Already done** |

Direction rule for the Route Planner (from `config/priors/c3.yaml` place kinds): origin
`port`/`icd` and destination `cluster` → import; origin `cluster` and destination `port`/`icd`
→ export; anything else (cluster → cluster) → no border, no card.

---

## 2. The design, checked against the data and the project's rules

Measured on the live data loaded on 2026-11-18 (17,025 current measures; 770 cells):

| Market | Cells with a number | No single number | No tariff line | Stale (annual WITS) | Highest duty |
|---|---|---|---|---|---|
| USA | 72 | **75** | 7 | 0 | 32.2 % |
| GBR | 146 | 1 | 7 | 0 | 12.0 % |
| EUN | 107 | 40 | 7 | 147 | 12.0 % |
| JPN | 91 | 56 | 7 | 147 | 7.5 % |
| CAN | 140 | 7 | 7 | 147 | 18.0 % |

What that decides:

| Check | Finding | Design consequence |
|---|---|---|
| Unresolved share | 179 of 770 cells (23 %), 75 of 154 in the US | Unresolved cells get their own look: a hatched cell with the **floor** ("≥ 16.5 %", the base) and an icon with a reason, never blank and never a guess |
| Lines per cell | US/UK average 5.8 national lines, max 79 | Cells show a **range** (min–max) when lines differ; the drawer groups lines with the same rate ("6 lines at 16.5 %") instead of 79 rows |
| Staleness | Every EU, Japan and Canada cell uses 2023 WITS | A "2023" chip on the column header and a stale icon in the cell, not 147 separate warnings |
| No line | HS 960290 (empty capsules) has no line in any market | **Data error (G-10):** HS 960290 does not exist (heading 9602 has only 9602.00). Proposal: change the pharma pack to `960200` (Q-26). Until then the row says "no tariff line: check the HS code" |
| Colour semantics | 05-ui-design §2: status colours (ok/warn/danger) are reserved and need an icon and a label | The heatmap uses the **sequential depth ramp** (one hue), not red/amber/green. The ramp is in the brief but not in `globals.css` (Q-22) |
| One source per view (A-111) | Tariffs are real; the Supplier Network shows only synthetic scenarios | Precedent: the Route Planner uses the real road graph in every mode. Proposal: tariffs are real reference data with **their own badge** on their own card, the page badge unchanged (Q-23) |
| Badges (rule 3) | Every C6 endpoint returns `meta.mode` and `meta.sources` | Every tariff card carries `Provenance` in its footer, as 17 files already do |
| Honesty (rule 3, "nothing fabricated") | Preferences assume the rules of origin are met; EU table is hand-kept and flagged verify | A note "assumes rules of origin are met" in the drawer; EU cells show a "hand-kept table, unverified" chip (as agreed: keep it flagged) |
| Latency (rule 7) | Matrix 35 ms median, product 42–50 ms on live data | Server page fetches overview + matrix in parallel; the drawer loads on click through a server action (the Radar's pattern) |
| Size | Matrix payload 203 KB for 770 cells | Default view: one industry (garments: 12 products × 5 markets × 1 origin at a time) ≈ 60 cells; "compare origins" switches the cell grid to origins |
| 1280 px | 5 market columns + product name should fit at 1280 px (≈ 180 px each: an estimate until the screenshot) | Matrix as a real `<table>` with sticky first column; no horizontal scroll at 1280 |
| Accessibility | `e2e/a11y.spec.ts` runs axe on 9 pages × 2 themes | Add `/tariffs` to its `PAGES`; cells are buttons with a text value, not colour alone |

---

## 3. The Tariff Monitor page: shape

The shape follows the reference (Disruption Radar) where the roles are the same, and adds two
roles the Radar does not have (the matrix and the KPI row). The tree, top to bottom:

```
page (app shell, nav rail entry "Tariff Monitor", icon `Landmark` from lucide-react: confirm on install)
  h1 "Tariff Monitor" + one-line subtitle                      (8 of 8 pages)
  Suspense skeleton while the server page loads                (6 of 8 pages)
  TariffWorkbench (client)
    toolbar row
      chips: industry  [Garments] [Pharma]                     (Radar's chip nav)
      chips: view      [Compare markets] [Compare origins]
      origin select (Bangladesh default) | market select (in "compare origins")
      date chips: [Today] [After LDC transition] (after backend step 1)
      DataBadge (ml-auto)                                       (Radar's toolbar)
    KPI row (4 tiles, the KPI strip's look)
      changes in 30 days · notices in 30 days · markets live · feeds missing
    grid xl:grid-cols-5
      Card xl:col-span-3  "Duty by market"   — the matrix <table>
        rows = products (HS6 + name), columns = markets (or origins)
        cell = button: effective % (or range, or "≥ base" hatched), depth-ramp tint
        column header: market name + live / 2023 / hand-kept chip
        CardFooter: Provenance + "Information, not legal or customs advice"
      Card xl:col-span-2  "What changed"     — change feed <ol>
        item = button: market · reference · origin · old → new (+Δ pp) · date
        empty: "No changes yet: change detection starts with the second daily fetch"
        then "Official notices": Federal Register list (kind icon, title, link)
    detail Card (inline, below the grid; close button)        (Radar's EventDrawer)
      header: product name, HS6, market, origin; close X
      rate stack bar (base | preference | surcharges)          SVG, hand-written
      lines grouped by rate (code, description, %)            <table>
      components: role, reference, duty text, legal ref, source link
      notes (unresolved reasons, rules-of-origin note, stale year)
      changes for this product and market
      Provenance
    feed status (collapsible, the Glossary's <details>)
      live / hand-kept / missing feeds from /overview, with the to-do text
```

Data per region → endpoint (all exist, BACKEND.md §4): toolbar, KPIs and feed status ←
`GET /tariffs/overview`; matrix ← `GET /tariffs/matrix?industry&origin` (or `market` in
compare-origins); feed ← `GET /tariffs/changes` + `GET /tariffs/notices`; detail ←
`GET /tariffs/products/{hs6}?market&origin` via a server action; country chips ←
`GET /tariffs/origins/{iso3}`.

URL state, like the Radar's `?source=`: `?industry=garments&view=markets&origin=BGD` so a view
can be linked from the other pages' cards (`/tariffs?hs6=610910&market=USA&origin=BGD` opens
the detail card).

States: loading = skeleton (Suspense); failed load = `ErrorNote`; no data at all (fresh DB) =
"No tariff data yet: run `uv run c6 refresh`" card; unresolved and stale as in §2.

---

## 4. Map and drawer cards on existing screens

### 4.1 Route Planner: "Duty at the border" (T3)

- **Where:** an overlay on the route map, bottom right (`absolute right-2 bottom-2 z-10`), the
  same overlay pattern as the traffic control (top left) in `route-map.tsx`; collapsible to a
  chip so it never hides the route.
- **Form:** two optional selects after "TEU": **Cargo** (watched products, from
  `/tariffs/overview`) and, for an export, **Market** (USA, GBR, EUN, JPN, CAN). Empty = no card.
- **Export (cluster → port):** "T-shirts from Bangladesh into the US: 26.5 % (16.5 % + 10 %
  surcharge 9903.05.26) · Vietnam 29 % · Cambodia 26.5 %". If a surcharge has a
  `loaded_before` date: "goods loaded before 7 Aug 2025 were exempt" against the plan's P90
  arrival at the port (C3 ETA), which is the hook for the "ship before the cut-off" action
  (BACKEND.md §6 step 4).
- **Import (port/ICD → cluster):** "Bangladesh import duty on cotton yarn: no live feed yet
  (NBR schedule is PDF; LIVE_FEEDS.md §2 #6)" with a link to the Monitor. Honest, not empty.
- **Data:** `GET /tariffs/matrix?hs6&market&origin=BGD,VNM,KHM` (one small call after "Plan
  routes"). Badge: the card's own `DataBadge`.

### 4.2 Supplier Network: tariff card in the node drawer (T4)

- **Buyer site** (`type = customer_site`, country NL or US): "Duty on what this buyer orders
  from Bangladesh", one row per product it orders (from node detail `customers`/orders), with
  the competitor row beneath. The market comes from the node's ISO2 country (NL → EUN, US →
  USA; a small map in `lib/c6.ts`).
- **Overseas supplier** (country ≠ BD): "Bangladesh import duty on <products>: no live feed
  yet", with the link; plus, where useful, the US surcharge the supplier's country pays
  (context for sourcing shifts: China +12.5 % … unresolved).
- **Map hover:** none new. The geo map keeps its own hover; the card lives in the drawer
  (the map already shows many nodes, and a second popup would compete).
- **Badges:** the node drawer stays SYNTHETIC; the tariff card shows its own LIVE / REPLAY
  badge (Q-23).

### 4.3 Disruption Radar: "Tariff check" on trade-policy events (T5)

- In `EventDrawer`, when `type = TRADE_POLICY_SANCTION`: a card with the schedule's view for
  the event's places and industries (e.g. Bangladesh + garments → US, UK, EU rates for the
  garment products, latest changes, matching Federal Register notices by country).
- Says plainly: "News says …; the schedule says …". Without the C2 link (T7) it matches by
  country and industry only, which the card states.

### 4.4 Control Tower: one brief line (T6)

- `/brief` gets one sentence when `tariff_change` has rows in the last 7 days: "3 tariff
  changes this week: US 9903.05.26 (Bangladesh) 10 % → 15 % …", citing the change rows, as
  every brief sentence cites rows. No new card.

---

## 5. The checklist the page tasks carry

`Tariff Monitor against workbench page (a server page.tsx under app/(app) that renders one
client workbench from components/<area>/, with a visual card, a list card and an inline detail
card) — from Disruption Radar, 5 members of 8 candidates in apps/web/app/(app) (members: radar,
network, routes, quality, ports; not members: Control Tower, Scenario Studio, Data & Models —
dashboard or report pages), read 2026-11-18`

- [ ] page title — `<h1 className="mb-1 text-xl font-semibold tracking-tight">` + `<p
      className="mb-4 text-sm text-muted">` subtitle in `page.tsx` — the majority, 8 of 8 pages
      (search: `text-xl font-semibold tracking-tight` over `app/(app)/**/page.tsx`)
- [ ] loading — `<Suspense fallback={<div className="skeleton h-[…] w-full" />}>` around an
      async server component — the majority, 6 of 8
- [ ] failed load — the shared `ErrorNote` from `components/kpi-strip` — the shared piece,
      16 files
- [ ] data access — server: `api()` from `lib/api/server`; client detail: a server action in
      `app/(app)/tariffs/actions.ts` — the majority, 5 of 5 members with client detail
      (network, ports, quality, radar, routes)
- [ ] types — `lib/c6.ts` re-exporting `components["schemas"]` from `lib/api/types.ts`
      (`npm run gen:api` after the OpenAPI change) — the majority, 5 of 5 `lib/cN.ts`
- [ ] cards — `Card`, `CardHeader` (title + one-line subtitle), `CardFooter` from
      `components/ui/card` — the shared piece, 23 files
- [ ] badge and provenance — `DataBadge` in the toolbar, `Provenance` in card footers from
      `components/data-badge` — the shared piece, 17 files
- [ ] filter chips — `<nav aria-label>` of `Link href="?key=…" scroll={false}` with
      `aria-current`, the Radar's classes — the reference, 3 files write it
- [ ] detail — an inline `Card` below the grid with an `h2 text-base font-semibold` header and
      a close button (`X`, `aria-label`) — the majority, 2 of 2 drawers (EventDrawer,
      NodeDrawer)
- [ ] tables — plain `<table>`: `w-full text-sm` for a table in a page card (4 of 4:
      ships-board, sources-table, port-view, quality-lab), `w-full text-xs` for a table inside
      a drawer or panel (4 of 4: node-drawer ×2, whatif-panel, event-drawer) — the majority per
      position; the matrix is `text-sm`, the detail card's lines table `text-xs`
- [ ] charts — hand-written SVG with theme variables; no chart library in `package.json` —
      7 of 7 chart components (whatif-panel, fan-chart, gate-flows, port-view, scenario-port,
      spc-chart, pareto-chart)
- [ ] values — theme tokens only (`bg-surface`, `border-border`, `text-muted`,
      `--radius-card`, `--radius-control`, `--series-*`), gaps on Tailwind's 4 px steps (169 of 169 uses;
      `gap-1`…`gap-4` in 166, `gap-6` twice, `gap-0` once), numbers in `.tabular` (63 uses); depth ramp per Q-22
- [ ] not copied from the Radar: its event icons and severity bar, its `?source=` keys, its map
      card and its h-[560px] heights (Radar-specific); and anything it hand-writes that has a
      shared piece (none found)

Left out on purpose: the nav-rail entry and e2e lists (identical in every page, in the task
text instead); positions with no convention: none on this page.

---

## 6. What the UI needs from the backend first

| Need | Status | Owner task |
|---|---|---|
| All six read endpoints | built | — |
| `lib/api/types.ts` regenerated | to do (`npm run gen:api`) | T1 |
| Matrix filter by `industry` and `origin` | built | — |
| "After LDC transition" view | backend step 1 (graduation.yaml) | before T2's date chips (T2 ships without them) |
| Node country ISO2 → market code | small map in `lib/c6.ts` | T4 |
| Route Planner: product list | `/tariffs/overview.products` | T3 |
| C2 tariff fields (direction, market, rate, HS, date) | backend (T7) | T7 |
| HS 960290 fix | Q-26 | — |

---

## 7. Verification (how each task is proven)

1. **Independent check** per page with `ui-consistency:verifying`, by an agent that did not
   write it, against §5's checklist; the check is calibrated once first on a scratch copy of
   the Radar with one role planted wrong (task T0).
2. **The project's checks** (AGENTS.md §8): `npm run typecheck`, `npm run lint`, Playwright
   e2e (a `tariffs.spec.ts` like the Radar's: page loads, matrix has 12 garment rows, a cell
   opens the detail card with `9903.05.26`, the feed lists notices, badges present), and
   `/tariffs` added to `a11y.spec.ts` and `sources.spec.ts` `PAGES`.
3. **Screenshots** of every changed page in light and dark at 1280 px into
   `docs/screenshots/` (tariff-monitor-*, route-planner-tariff-*, network-tariff-*).
4. **Numbers against the source**: the e2e test asserts the US/BGD T-shirt cell reads 26.5 %
   and the UK/BGD cell 0 %, the same numbers the backend tests pin.

---

## 8. Tasks

Status of a task: unticked is `todo`, ticked is `done`, and `parked — <why>` stays unticked
with its reason on the line.

### Decided

- "Keep it flagged" (the EU preferences table stays marked unverified in the data and the UI)
  — user, 2026-11-18. Applies to T2 (EU column chip) and T4.

### Tasks

- [ ] **T0 Calibrate the check.** Copy `apps/web/components/radar/workbench.tsx` into a
      scratch worktree outside the checkout, change one role (e.g. write the toolbar badge as
      a plain `<span>` instead of `DataBadge`), and give it to a separate agent with
      `ui-consistency:verifying` and the §5 checklist, told only that the copy differs
      somewhere. If the planted difference is not reported, stop: the check is blind for it.
- [ ] **T1 Types and theme.** `npm run gen:api` (picks up `/tariffs/*`); add `lib/c6.ts`
      (types, `pct()` formatter, market and origin names, ISO2 → market map).
      `parked — waiting on Q-22` for the depth-ramp tokens in `app/globals.css` (light and dark).
- [ ] **T2 Tariff Monitor page** — write `app/(app)/tariffs/page.tsx`,
      `app/(app)/tariffs/actions.ts`, `components/tariffs/{workbench,matrix,change-feed,
      detail-card,rate-stack}.tsx`, the nav-rail entry (`Landmark` or `Scale` from lucide-react, after Disruption Radar),
      following `components/radar/workbench.tsx`, against the §5 checklist (carried in full
      above).
      Must not be copied from the Radar: its event icons and severity bar, `?source=` keys,
      map card, fixed heights.
      Not in this task: the "After LDC transition" chips (backend step 1).
      1. Re-read the checklist before writing — do not work from memory.
      2. Report the page ready for its check; the checker of this kind (with
         `ui-consistency:verifying`, never the writer or the calibrated agent) checks it; fix
         what it reports.
      3. Report the status here: `done` once the check has passed, or `parked — <why>`.
- [ ] **T3 Route Planner: "Duty at the border" card** — `components/routes/planner.tsx`
      (Cargo and Market selects, written like the existing `select()` helper: `label` +
      `select` with the same classes) and `components/routes/route-map.tsx` (overlay,
      bottom right, the traffic control's overlay pattern), following the Route Planner's own
      form and overlay (sized as one region of an existing page: `ui-consistency:adjusting`).
      Checklist: form fields — the page's `select()` helper, 2 of 2 selects; overlay —
      `absolute … z-10` like the traffic control, 1 of 1; card body — `Card`-like section with
      `Provenance`; values through the theme. Must not be copied: the traffic control's
      buttons. Steps 1–3 as in T2.
- [ ] **T4 Supplier Network: tariff card in the node drawer** —
      `components/network/node-drawer.tsx`, a section like the drawer's existing sections,
      with its own `DataBadge`. `parked — waiting on Q-23` (real tariffs on a synthetic page).
      Steps 1–3 as in T2.
- [ ] **T5 Disruption Radar: "Tariff check" card** — `components/radar/event-drawer.tsx`,
      shown for `TRADE_POLICY_SANCTION` only, written like the drawer's recommendation
      section. Steps 1–3 as in T2.
- [ ] **T6 Control Tower brief line** — `apps/api/.../routers/brief.py` (one sentence citing
      `tariff_change` rows) and its test; the brief component unchanged. Steps 1–3 as in T2
      (the check is the brief's existing e2e plus the new line).
- [ ] **T7 C2 tariff fields (backend for T5 and the "announced" chip)** — extraction of
      direction, market, rate, HS chapter, effective date; only raises feed buffers (G-9);
      `parked — waiting on Q-25`.
- [ ] **Close the plan** — once every task is done or parked: report what is under *Decided*
      with the result.

---

## 9. Questions waiting on you (batched, AGENTS.md §7)

| Q-ID | Context | Options | Recommendation |
|---|---|---|---|
| Q-22 | The heatmap needs the brief's depth ramp (05 §2); it is not in `globals.css`, and the one existing use (Pareto) fakes it with `--primary` opacity | (a) add `--depth-100…900` tokens (light and dark) to the theme · (b) `--primary` with opacity, like the Pareto chart | (a): it is the brief's validated ramp; one theme change, used by T2 and later heatmaps |
| Q-23 | Supplier Network shows synthetic scenarios only; the "one data source per view" rule (A-111) | (a) tariffs are real reference data shown on their own card with their own badge (like the real road graph in the Route Planner) · (b) no tariffs on synthetic pages | (a), with the card's own LIVE badge |
| Q-24 | Route Planner form | (a) add optional Cargo + Market selects · (b) no form change: the card shows all garment products | (a): one product makes the card short and specific |
| Q-25 | C2 treats tariff cuts as disruptions (G-9) | (a) T7: extract direction and only raises feed buffers · (b) leave C2 as is | (a) |
| Q-26 | HS 960290 (empty capsules) does not exist: heading 9602 has only 9602.00 | (a) change the pharma pack to `960200` (re-seed; C1 world unchanged otherwise) · (b) keep, and show "no tariff line" | (a) |

While you decide: T0, T1 (without the tokens), T2 (without the date chips), T3, T5 and T6 do
not wait on any of these except where marked.

---

## 10. What was read for this plan (cost)

`ui-consistency` skills read: finding-patterns (with words.md, checklist.md), values,
planning (with plan-file.md). About 25 project files opened and about 30 searches run, all in
this session (estimate; not every count was kept). Not evaluated: the web app's runtime
behaviour (no browser run this turn; that is §7's job), and contrast numbers (only measured
when accessibility is asked for; the axe check in §7 covers it).
