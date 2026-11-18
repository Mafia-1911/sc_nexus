import { expect, type Page, test } from "@playwright/test";

/** Tariff Monitor (C6, UI_PLAN T2–T6). Values are checked against the API's own answer for the
 *  same cell, so the test proves the page shows what the data says, whatever the live data is. */
const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SHOTS = process.env.E2E_SHOTS ?? "../../docs/screenshots";

type Cell = { market: string; hs6: string; origin: string; effective_pct_min: number | null; effective_pct_max: number | null; is_resolved: boolean; is_ceiling: boolean; base_pct: number | null; n_lines: number };

function pct(v: number | null): string {
  if (v === null) return "—";
  if (v === 0) return "Free";
  return `${Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1)}%`;
}

/** The same rule as lib/c6.ts cellText, applied to the API's numbers. */
function expected(c: Cell): string {
  if (c.n_lines === 0) return "—";
  if (!c.is_resolved || c.effective_pct_max === null) return c.base_pct === null ? "varies" : `≥ ${pct(c.base_pct).replace("Free", "0%")}`;
  const lo = c.effective_pct_min ?? c.effective_pct_max;
  const text = lo === c.effective_pct_max ? pct(lo) : `${pct(lo).replace("Free", "0%")}–${pct(c.effective_pct_max)}`;
  return c.is_ceiling && c.effective_pct_max > 0 ? `≤ ${text}` : text;
}

async function apiCells(page: Page, query: string): Promise<Cell[]> {
  const res = await page.request.get(`${API}/api/v1/tariffs/matrix?${query}`);
  expect(res.ok()).toBeTruthy();
  return (await res.json()).data.cells as Cell[];
}

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem("theme", t);
  }, theme);
}

test("Tariff Monitor: matrix values equal the API's, legend, KPIs and feed status", async ({ page }) => {
  await page.goto("/tariffs");
  await expect(page).toHaveTitle(/Tariff Monitor/);
  const matrix = page.getByTestId("tariff-matrix");
  await expect(matrix).toBeVisible();
  const cells = await apiCells(page, "industry=garments&origin=BGD");
  expect(cells.length).toBe(12 * 5); // 12 garment products × 5 markets
  for (const c of cells) {
    await expect(page.locator(`[data-cell="${c.market}:${c.hs6}:${c.origin}"]`).locator("span").first()).toHaveText(expected(c));
  }
  await expect(page.getByTestId("tariff-legend")).toContainText("Free");
  await expect(page.getByTestId("tariff-legend")).toContainText("> 25%");
  // every market column fits at 1280 px (no horizontal scroll hides Canada)
  const box = await page.locator('[data-cell="CAN:610910:BGD"]').boundingBox();
  expect(box && box.x + box.width).toBeLessThanOrEqual(1280);
  expect(cells.some((c) => c.market === "CAN" && c.is_ceiling)).toBeTruthy();
  await expect(page.getByTestId("tariff-kpis")).toContainText("Markets with a live schedule");
  await page.getByTestId("feed-status").locator("summary").click();
  await expect(page.getByTestId("feed-status")).toContainText("EU-TARIC");
  await expect(page.getByTestId("feed-status")).toContainText("Missing");
});

test("Tariff Monitor: a cell opens how the rate is made up, with sources", async ({ page }) => {
  await page.goto("/tariffs");
  const [c] = await apiCells(page, "hs6=610910&market=USA&origin=BGD");
  await page.locator('[data-cell="USA:610910:BGD"]').click();
  const detail = page.getByTestId("tariff-detail");
  await expect(detail).toBeVisible({ timeout: 15_000 });
  await expect(detail).toContainText("into United States");
  await expect(page.getByTestId("detail-rate")).toContainText(expected(c));
  await expect(page.getByTestId("rate-stack")).toBeVisible();
  await expect(page.getByTestId("detail-components")).toContainText("Base rate (MFN)");
  await expect(page.getByTestId("detail-compare").locator("tbody tr")).toHaveCount(7);
  // several surcharge lines whose stacking is not stated are an upper bound, never a fact
  const detailApi = (await (await page.request.get(`${API}/api/v1/tariffs/products/610910?market=USA&origin=CHN`)).json()).data;
  const chnLine = detailApi.markets[0].lines[0];
  const surcharges = chnLine.components.filter((x: { role: string }) => x.role === "additional").length;
  if (surcharges > 1) {
    await expect(page.getByTestId("detail-compare").locator("tr", { hasText: "China" })).toContainText(`up to +`);
  }
  await expect(detail.locator('a[href^="https://hts.usitc.gov/"]').first()).toBeVisible();
  await expect(detail).toContainText("not legal or customs advice");
  // another origin from the comparison table
  await page.getByTestId("detail-compare").getByRole("button", { name: "Viet Nam" }).click();
  await expect(detail).toContainText("from Viet Nam");
  await page.getByRole("button", { name: "Close product details" }).click();
  await expect(detail).toBeHidden();
});

test("Tariff Monitor: compare origins, pharma, and a deep link", async ({ page }) => {
  await page.goto("/tariffs?view=origins&market=GBR&industry=pharma");
  const cells = await apiCells(page, "industry=pharma&market=GBR");
  expect(cells.length).toBe(10 * 7); // 10 pharma products × 7 origins
  for (const c of cells.slice(0, 14)) {
    await expect(page.locator(`[data-cell="${c.market}:${c.hs6}:${c.origin}"]`).locator("span").first()).toHaveText(expected(c));
  }
  await page.goto("/tariffs?hs6=610910&market=GBR&origin=BGD");
  await expect(page.getByTestId("tariff-detail")).toContainText("into United Kingdom");
  await expect(page.getByTestId("detail-components")).toContainText("Comprehensive Preferences (1062)");
});

test("Tariff Monitor: news, schedule changes and notices match the API", async ({ page }) => {
  await page.goto("/tariffs");
  const news = (await (await page.request.get(`${API}/api/v1/tariffs/news?limit=30`)).json()).data as { title: string; confirmed: boolean; direction: string }[];
  const notices = (await (await page.request.get(`${API}/api/v1/tariffs/notices?limit=25`)).json()).data as unknown[];
  await expect(page.getByRole("tab", { name: /News/ })).toContainText(`(${news.length})`);
  if (news.length) {
    await page.getByRole("tab", { name: /News/ }).click();
    const items = page.getByTestId("news-item");
    await expect(items).toHaveCount(news.length);
    await expect(items.first()).toContainText(news[0].title.slice(0, 40));
    await expect(items.first()).toContainText(news[0].confirmed ? "In the schedule" : "Announced, not in the schedule yet");
  }
  await page.getByRole("tab", { name: /Official notices/ }).click();
  await expect(page.getByTestId("notice-item")).toHaveCount(notices.length);
});

test("Route Planner: duty at the border for an export leg", async ({ page }) => {
  await page.goto("/routes?origin=gazipur&dest=BDCGP");
  await page.locator('select[name="hs6"]').selectOption("610910");
  await page.locator('select[name="market"]').selectOption("USA");
  await page.getByTestId("plan-route").click();
  const card = page.getByTestId("border-duty");
  await expect(card).toBeVisible({ timeout: 30_000 });
  const cells = await apiCells(page, "hs6=610910&market=USA&origin=BGD&origin=VNM&origin=KHM");
  for (const c of cells) await expect(card.locator(`[data-origin="${c.origin}"]`)).toHaveText(expected(c));
  await expect(card.locator("[data-mode]")).toHaveCount(1);
  await expect(card.getByRole("link", { name: /How it is made up/ })).toHaveAttribute("href", "/tariffs?hs6=610910&market=USA&origin=BGD");
});

test("Route Planner: an import leg says the Bangladesh feed is missing", async ({ page }) => {
  await page.goto("/routes?origin=BDCGP&dest=gazipur");
  await page.locator('select[name="hs6"]').selectOption("520512");
  await expect(page.locator('select[name="market"]')).toBeDisabled();
  await page.getByTestId("plan-route").click();
  await expect(page.getByTestId("border-duty")).toContainText("no live feed yet", { timeout: 30_000 });
});

test("Screenshots: Tariff Monitor and the route card, light and dark", async ({ page }) => {
  await page.goto("/tariffs");
  await page.locator('[data-cell="USA:610910:BGD"]').click();
  await expect(page.getByTestId("tariff-detail")).toBeVisible({ timeout: 15_000 });
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(300);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${SHOTS}/tariff-monitor-${theme}.png`, fullPage: true });
  }
  await page.goto("/routes?origin=gazipur&dest=BDCGP");
  await page.locator('select[name="hs6"]').selectOption("610910");
  await page.getByTestId("plan-route").click();
  await expect(page.getByTestId("border-duty")).toBeVisible({ timeout: 30_000 });
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${SHOTS}/route-planner-tariff-${theme}.png`, fullPage: true });
  }
});

type GNode = { id: string; type: string; country: string | null; kind: string };

async function nodes(page: Page): Promise<GNode[]> {
  const res = await page.request.get(`${API}/api/v1/graph?scenario=cyclone_supplier_delay`);
  return (await res.json()).data.nodes as GNode[];
}

test("Supplier Network: a buyer abroad shows the duty into its market (T4)", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "cyclone_supplier_delay", url: baseURL! }]);
  const buyer = (await nodes(page)).find((n) => n.type === "customer_site" && n.country === "NL")!;
  await page.goto(`/network?node=${buyer.id}`);
  const card = page.getByTestId("node-tariffs");
  await expect(card).toContainText("Duty into European Union", { timeout: 20_000 });
  await expect(card.getByTestId("rate-rows").first()).toBeVisible({ timeout: 20_000 });
  // values equal the API's for the first product listed
  const first = (await card.locator("p.font-medium").first().textContent()) ?? "";
  const hs6 = first.match(/HS (\d{6})/)?.[1];
  expect(hs6).toBeTruthy();
  const cells = await apiCells(page, `hs6=${hs6}&market=EUN&origin=BGD&origin=VNM&origin=CHN`);
  for (const c of cells) await expect(card.getByTestId("rate-rows").first().locator(`[data-origin="${c.origin}"]`)).toHaveText(expected(c));
  // the firm is synthetic, the tariff card real: its own badge, marked as reference data
  await expect(card).toHaveAttribute("data-reference", "tariffs");
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(300);
    await card.scrollIntoViewIfNeeded();
    await page.getByTestId("node-drawer").screenshot({ path: `${SHOTS}/network-tariff-${theme}.png` });
  }
});

test("Supplier Network: an overseas supplier says the Bangladesh feed is missing; a customer in an unwatched market shows no card", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "cyclone_supplier_delay", url: baseURL! }]);
  const all = await nodes(page);
  const supplier = all.find((n) => n.type === "raw_material_supplier" && n.country === "IN")!;
  await page.goto(`/network?node=${supplier.id}`);
  await expect(page.getByTestId("node-tariffs")).toContainText("no live feed yet", { timeout: 20_000 });
  const lk = all.find((n) => n.type === "customer_site" && n.country === "LK")!;
  await page.goto(`/network?node=${lk.id}`);
  await expect(page.getByTestId("node-drawer")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("node-tariffs")).toHaveCount(0);
});

test("Disruption Radar: a real trade-policy event gets a Tariff check (T5)", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "", url: baseURL! }]);
  const res = await page.request.get(`${API}/api/v1/events?scenario=&source=news&limit=80`);
  const events = ((await res.json()).data ?? []) as { id: string; type: string; title: string }[];
  const trade = events.find((e) => e.type === "TRADE_POLICY_SANCTION");
  test.skip(!trade, "no real trade-policy event in the news window right now");
  await page.goto("/radar?source=news");
  await page.getByTestId("event-feed").locator("button", { hasText: trade!.title.slice(0, 30) }).first().click();
  await expect(page.getByTestId("tariff-check")).toContainText("The schedule says today", { timeout: 20_000 });
});

test("Control Tower: the brief's tariff line links to the Tariff Monitor (T6)", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "", url: baseURL! }]);
  const brief = (await (await page.request.get(`${API}/api/v1/brief?scenario=`)).json()).data as { lines: { text: string }[] };
  const line = brief.lines.find((l) => l.text.startsWith("Tariffs"));
  test.skip(!line, "no tariff change or pending tariff news this week");
  await page.goto("/");
  await expect(page.getByTestId("daily-brief")).toContainText("Tariffs");
  await expect(page.getByTestId("daily-brief").locator('a[href^="/tariffs"]').first()).toBeVisible();
});
