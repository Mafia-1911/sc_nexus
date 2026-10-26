# ADR-015: Web app: Next.js 16 with Cache Components, a typed server client and a live socket

Status: accepted   Date: 2026-10-27

**Context:** M2 needs the themed shell, the Control Tower (KPI strip, live anchorage map, alert
feed, shipments) and Data & Models, runnable with `docker compose up` and on a laptop
(D-05, D-10, 05-ui-design). Every number on screen must carry its data mode (rule 3), and no
key may reach the browser (rule 8).

**Decision:**
- **Next.js 16.4 App Router with Cache Components** (`cacheComponents: true`) and Partial
  Prefetching. Pages prerender a static shell; anything that reads the API, cookies (the
  scenario switch) or the runtime brand sits inside `<Suspense>` and streams. `api()`,
  `currentScenario()` and `brandName()` call `connection()` first, so nothing request-bound is
  baked in at build time. Placeholder pages render a small dynamic marker because their
  titles carry the runtime brand.
- **Typed client on the server only:** `openapi-typescript` generates `lib/api/types.ts` from
  `docs/api/openapi.json` (`npm run gen:api`), and `openapi-fetch` calls the API from server
  components (`API_URL`, `cache: "no-store"`). The browser never calls the REST API.
- **Live positions over `/ws/live`:** the browser opens the API's WebSocket directly
  (`NEXT_PUBLIC_WS_URL`, inlined at build, default `ws://127.0.0.1:8000/ws/live`). The socket
  carries GeoJSON snapshots only and needs no credentials.
- **Map:** MapLibre GL 6 with OpenFreeMap tiles (ADR-006), restyled from the theme tokens; the
  vessels are a native circle layer. deck.gl waits until routes and heatmaps need it (M5).
  MapLibre 6 resolves its worker relative to its own module, which a bundled chunk breaks, so
  `scripts/vendor-maplibre.mjs` copies the worker to `public/vendor/` before `dev` and `build`
  and the map calls `setWorkerUrl`.
- **Components:** shadcn-style local components (`cva`, `tailwind-merge`, Tailwind v4 tokens
  from 05 §2) without the shadcn CLI or Radix yet. Primitives that need Radix (dialog, popover,
  tabs) come in through the shadcn CLI when a page needs them. Fonts (Inter, Noto Sans Bengali,
  JetBrains Mono) are self-hosted by `next/font`.
- **Runtime:** `output: "standalone"`; `apps/web/Dockerfile` builds it (node 24) for the `web`
  compose service.
- **Smoke test:** Playwright (`make e2e`) checks titles, KPI badges, the live map, scenario
  switching, licences and the theme toggle, and writes light and dark screenshots at 1280 px to
  `docs/screenshots/`.

**Alternatives considered:** client-side fetching with React Query (exposes the API surface to
the browser and duplicates badges logic); server-sent events through Next (an extra hop for a
stream the API already serves); deck.gl for 80 points (heavier, no gain yet); committing the
MapLibre worker into `public/` (drifts on upgrade).

**Consequences:** + fast static shell, typed contract from one OpenAPI file, no keys in the
browser, one-command stack. − Cache Components rules are strict: a new page that reads
runtime data outside `<Suspense>` fails the build, which is the intended guard. − The WebSocket
URL is fixed at build time; a hosted deployment (Vercel, later) rebuilds with its own URL.
