# 05 · UI and design system: "Tidewater"

**TL;DR.** Calm, legible and oceanic. Deep-navy "Abyss" is the dark default for the control-tower feel, and the light theme is "Shallows". Colour is reserved for signal, and uncertainty is always visible. Every number shows where it came from (a LIVE, REPLAY or SYNTHETIC badge). The tokens below were **validated** on 2026-10-26: UI text meets WCAG AA (≥ 4.5:1), input borders ≥ 3:1, and the chart palette passed lightness-band, chroma, CVD-separation (adjacent ΔE ≥ 8 target), normal-vision (≥ 15) and contrast checks in both modes. If you change a hex value, re-run a contrast and CVD validator.

## 1. Principles

1. **Signal over decoration.** Surfaces stay quiet. Colour appears where state changes (alerts, risk, selection).
2. **Show uncertainty.** Use fan charts, P10–P90 bands, "likely 3–5 days" phrasing and on-time probabilities. Never show a bare point estimate for a forecast.
3. **Provenance everywhere.** Data badges, an "as of" time and a sources popover on every card.
4. **One story per screen.** Each page answers one persona question (see `01-product.md` §3).
5. **Gentle motion.** 150–250 ms ease-out. A "ripple" metaphor for cascades and propagation. Honour `prefers-reduced-motion`.

## 2. Tokens (Tailwind v4: `apps/web/styles/tokens.css`)

```css
@import "tailwindcss";

/* Light: "Shallows" */
:root {
  color-scheme: light;
  --bg: #f3f8fa;  --surface: #ffffff;  --surface-2: #e8f1f5;  --chart-surface: #fafcfd;
  --border: #c9dce5;            /* hairlines, decorative */
  --border-strong: #6f8a9b;     /* inputs, focusable outlines: ≥3:1 on all light surfaces */
  --text: #0a2233;  --text-muted: #4a6578;               /* 15.2:1 / 5.7:1 on bg */
  --primary: #0b7a80;  --on-primary: #ffffff;  --focus: #0b7a80;   /* 5.1:1 */
  --info: #1f6fa8;  --ok: #1e7a4f;  --warn: #9a5b00;  --danger: #b83a44;   /* all ≥5.3:1 as text */
  --accent-sand: #bd8400;       /* highlights only; not for body text */
  /* categorical chart slots, fixed order, never cycled */
  --series-1: #1f6fc5; /* ocean   */  --series-2: #e5603f; /* coral   */
  --series-3: #0e9f95; /* lagoon  */  --series-4: #bd8400; /* sand    */
  --series-5: #db6f9e; /* anemone */  --series-6: #2f8a2f; /* kelp    */
  --series-7: #6650d2; /* urchin  */
}

/* Dark: "Abyss" (OS setting, unless the user forced light) */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #06131f;  --surface: #0b1f31;  --surface-2: #112a40;  --chart-surface: #0c1f30;
    --border: #1d3b55;  --border-strong: #5a7f9e;          /* ≥3.4:1 on all dark surfaces */
    --text: #e3eef4;  --text-muted: #93afc2;               /* 14.2:1 / 7.3:1 on surface */
    --primary: #3cc4bf;  --on-primary: #04222a;  --focus: #8fe3da;
    --info: #6fb7e9;  --ok: #5cc995;  --warn: #f2b65e;  --danger: #f2777a;
    --accent-sand: #e6d3a3;
    --series-1: #3d88e0;  --series-2: #e06a48;  --series-3: #16a89c;  --series-4: #c08300;
    --series-5: #d7699a;  --series-6: #2f9a3a;  --series-7: #8e82ea;
  }
}
/* Explicit toggle wins both ways */
:root[data-theme="dark"] { /* repeat the dark block above */ }

@theme inline {
  --color-bg: var(--bg); --color-surface: var(--surface); --color-surface-2: var(--surface-2);
  --color-border: var(--border); --color-border-strong: var(--border-strong);
  --color-text: var(--text); --color-muted: var(--text-muted);
  --color-primary: var(--primary); --color-on-primary: var(--on-primary);
  --color-info: var(--info); --color-ok: var(--ok); --color-warn: var(--warn); --color-danger: var(--danger);
  --radius-card: 14px; --radius-control: 10px;
  --font-sans: "Inter", "Noto Sans Bengali", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}
body { background: var(--bg); color: var(--text); }
```

**Sequential "depth" ramp** (one hue, light to dark; for heatmaps, H3 density and risk magnitude):
`100 #d5eef0 · 200 #aadfe3 · 300 #7fcbd3 · 400 #52b2bf · 500 #2b95a6 · 600 #187789 · 700 #0f5d70 · 800 #0b4558 · 900 #082f40`

- *Continuous, light mode:* 100 → 900. The lightest step means "near zero" and may fade into the surface.
- *Ordinal (discrete tiers), light mode:* start at **400** (validated: 2.41:1 at the light end).
- *Dark mode:* flip the anchor, so low values sit near the surface and high values are bright. The validated ordinal run is 600 → 100.

**Diverging** (forecast vs baseline, delta CO2e): ocean (`--series-1`) ↔ coral (`--series-2`), with a neutral grey midpoint (light `#eef1f3`, dark `#2a3a48`) and equal step counts on each arm.

**Status colours** (`ok`, `warn`, `danger`, plus `info`) are reserved. They always come with an **icon and a label**, and are never used as series colours.

**Chart palette rules:**

- Assign series colours in slot order, and keep each entity's colour stable when filters change (colour follows the entity, never its rank).
- Use at most 7 categorical series; fold the rest into "Other".
- Scatter plots, maps and small multiples use **at most 3** categorical series. Slots 1–3 passed the all-pairs check in both modes.
- In light mode, anemone (3.0:1), lagoon (3.2:1) and sand (3.2:1) sit just above 3:1. For thin or small marks, add direct labels or a table view.

## 3. Layout and components

- **App shell:** a left rail with icons and labels (Control Tower, Ports & Vessels, Supplier Network, Disruption Radar, Route Planner, Quality Lab, Scenario Studio, Data & Models). The top bar holds a ⌘K command palette, the data-mode pill, a time-travel control (replay/backtest date) and the theme toggle.
- **Grid:** 12 columns, an 8 px spacing scale, 14 px card radius and 1 px hairline borders. Use soft shadows only on overlays.
- **Card anatomy:** title, a one-line "so what" subtitle, the content, then a footer with the source badges, "as of" time and an "Explain" link.
- **Components** (shadcn/ui based): `KpiTile` (value + delta + sparkline + interval), `DataBadge`, `AlertCard`, `EvidenceQuote`, `RecommendationCard` (action, expected value, confidence, Accept/Dismiss), `FanChart`, `ParetoChart`, `ExplainPanel` (top drivers), `EntityChip` (port, facility, vessel; links to its drawer), `TimelineScrubber`.
- **Empty, loading and error states** are designed, not left as defaults. Skeletons use a subtle "tide" shimmer, disabled under reduced motion.

## 4. Pages (each maps to a persona and a capability)

| Page | Main question | Key elements |
|---|---|---|
| **Control Tower** | What needs my attention now? | KPI strip (K-01, K-03, K-05, K-07); live map (vessels, anchorage density, active events); alert feed; "Today's brief" with citations; shipments-at-risk table |
| **Ports & Vessels** (C4) | When will vessels berth and leave, and how congested will it get? | Port switcher (CGP default); queue timeline + 14-day fan chart; vessel table (ETA, wait P10/P50/P90, berth h, drivers); vessel drawer with track replay; satellite panel (latest S1/S2 thumbnail + SAR count vs AIS count) |
| **Supplier Network** (C1) | Where are we fragile? | Graph ↔ geo map toggle; criticality leaderboard (dominators, downstream count, TTS vs TTR); node drawer; **what-if** panel (disable node / reduce capacity for N days) with a ripple animation and impact summary; inferred edges dashed |
| **Disruption Radar** (C2) | What happened, and does it affect us? | Event feed (type icon, severity, confidence, sources, corroboration chips); map and timeline; event detail (evidence quotes with links, linked entities, buffer recommendation); backtest mode |
| **Route Planner** (C3) | How do I move this cargo best? | O/D pickers (ports, ICDs, warehouses), cargo profile, deadline; preference sliders (time, cost, CO2e); **Pareto chart**; route cards (P50/P90, cost, CO2e, mode mix, on-time probability); map with mode-coloured legs; departure-window heat strip |
| **Quality Lab** (C5) | Is this batch OK, and what does a bad batch cost us? | Upload or stream; image grid with heatmap overlays and masks; batch board (AQL status); SPC charts per line; defect-risk forecast; impact panel (orders, inventory, delivery commitments) with "Replan" (C3) |
| **Scenario Studio** (NX) | What if…, and what should we do? | Scenario builder (event type, location, duration, intensity); run across capabilities; baseline vs scenario KPI table; action plan; export a one-page PDF/PNG |
| **Data & Models** | Can I trust this? | Source registry (mode, freshness, record counts, licence); model registry (metrics, cards, calibration plots); attributions |

## 5. Map

- MapLibre GL JS with an **OpenFreeMap** style (or self-hosted Protomaps), restyled with deep teal-navy water, muted slate and sand land, and quiet labels.
- deck.gl layers: `IconLayer` for vessels (rotated by heading, coloured by state: underway, anchored, berthed), `H3HexagonLayer` for anchorage density (depth ramp), `PathLayer` for routes (mode colours from series slots 1–4 plus a pattern for rail and barge), `ArcLayer` for supplier-to-port flows, and `PolygonLayer` for port zones and event areas.
- Interaction: hover tooltips with a hit target larger than the mark, click to open the entity drawer, and a time scrubber for replays.
- Attribution: © OpenStreetMap contributors, plus the tile provider. GFW, GDACS and the other sources are credited on the Data & Models page.

## 6. Graph visualisation

- Sigma.js + graphology with ForceAtlas2 (precomputed positions cached server-side), or a layered left-to-right flow layout (tiers).
- **Encodings:** node shape = type, node size = criticality (downstream value), fill = risk (depth ramp), ring = selected/affected, edge width = flow share, dashed edge = inferred.
- **What-if:** the disrupted node pulses once, then affected nodes light up in waves ordered by time-to-impact. A side panel shows TTS vs TTR bars and the orders at risk.

## 7. Chart rules (enforce in review)

- **Never use a dual-axis chart.** Use two charts, or index to a common base.
- Lines 2 px, markers ≥ 8 px, a 2 px surface gap between adjacent fills, recessive grid lines.
- Show a legend whenever there are ≥ 2 series, and direct-label up to 4 series. Text uses the text tokens, never the series colour.
- Hover crosshairs and tooltips by default. Every chart has a "view as table" toggle.
- Forecasts are **fan charts**: P50 line plus P10–P90 band, with a "now" marker separating history from forecast.

## 8. Accessibility and language

- WCAG 2.2 AA. Full keyboard navigation and visible focus (`--focus`, 2 px ring + 2 px offset).
- Never rely on colour alone: pair it with icons, labels, patterns or position.
- `prefers-reduced-motion` turns off the ripple and shimmer.
- Bangla text renders in Noto Sans Bengali. News items show the original language plus an English summary.
- Number formats: thousands separators, units always shown, BDT and USD with the currency symbol, and Asia/Dhaka times with a "BST" (Bangladesh Standard Time) label.

## 9. Copy tone

Plain, calm and specific: "Likely 3–5 days (80 %)", not "~4.1 days". Recommendations say what to do, why, at what cost and with what confidence. Never use alarmist red copy for low-confidence events.

## 10. Demo polish checklist (before G3)

- [ ] Golden path runs end to end in replay mode without network, in under 7 minutes.
- [ ] Light and dark screenshots of each page are in the README.
- [ ] No layout shift or spinner longer than 1 s on the golden path (precompute and warm the caches).
- [ ] Every number has a badge and a source popover. No "NaN", "undefined" or lorem ipsum.
- [ ] A 1366×768 laptop and a 1920×1080 projector both look right. Fonts are loaded locally (venue Wi-Fi).
- [ ] The Lighthouse accessibility score is ≥ 90 on every page.
