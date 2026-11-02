import { expect, type Page, test } from "@playwright/test";

const SHOTS = "../../docs/screenshots";
const BRAND = process.env.CPORTAL_BRAND_NAME ?? "ShipperFast";

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((t) => {
    document.querySelector("[data-idle]")?.removeAttribute("data-idle"); // the map repaints
    document.documentElement.dataset.theme = t;
    localStorage.setItem("theme", t);
    window.dispatchEvent(new CustomEvent("themechange", { detail: t }));
  }, theme);
}

async function waitForVessels(page: Page) {
  await expect(page.getByTestId("vessel-count")).toHaveText(/^[1-9]\d* vessels$/, { timeout: 30_000 });
  await mapIdle(page);
}

/** MapLibre's "idle": every tile drawn, no transition running (components/vessel-map.tsx). */
async function mapIdle(page: Page) {
  await expect(page.getByTestId("vessel-map")).toHaveAttribute("data-idle", "true", { timeout: 30_000 });
}

test.describe.configure({ mode: "serial" });

test("Control Tower: KPIs, badges, live map and alerts", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "cyclone_supplier_delay", url: baseURL! }]);
  await page.goto("/");
  await expect(page).toHaveTitle(new RegExp(`Control Tower · ${BRAND}`));
  const tiles = page.locator("[data-kpi]");
  await expect(tiles).toHaveCount(5);
  for (const tile of await tiles.all()) {
    await expect(tile.locator("[data-mode]")).toHaveCount(1);
  }
  await expect(page.locator('[data-kpi="vessels_at_anchorage"] [data-mode]')).toHaveAttribute("data-mode", "synthetic");
  await expect(page.locator('[data-kpi="co2e_week"]')).toContainText("Route Planner");
  await waitForVessels(page);
  await expect(page.getByTestId("alert-feed")).toContainText("SYN-01");
  // Ships at Chattogram (simulated port in a scenario): status filters and a dock estimate.
  await expect(page.getByTestId("ship-row").first()).toBeVisible();
  await expect(page.getByTestId("ship-filters")).toContainText("At anchorage");
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await mapIdle(page);
    await page.screenshot({ path: `${SHOTS}/control-tower-${theme}.png`, fullPage: true });
  }
});

test("Scenario switch: real data only shows the replay badge", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("data-select").selectOption("real:today");
  await expect(page.locator('[data-kpi="vessels_at_anchorage"] [data-mode]')).toHaveAttribute("data-mode", "replay", {
    timeout: 15_000,
  });
  await page.getByTestId("data-select").selectOption("scn:cyclone_supplier_delay");
  await expect(page.locator('[data-kpi="vessels_at_anchorage"] [data-mode]')).toHaveAttribute("data-mode", "synthetic", {
    timeout: 15_000,
  });
});

test("Control Tower, real data: no synthetic badge, real ships, sources open, dates", async ({ page, baseURL }) => {
  await page.context().addCookies([
    { name: "scenario", value: "", url: baseURL! },
    { name: "asof", value: "today", url: baseURL! },
  ]);
  await page.goto("/");
  await expect(page.locator('[data-kpi="vessels_at_anchorage"] [data-mode]')).not.toHaveAttribute("data-mode", "synthetic");
  await expect(page.getByTestId("ship-row").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("ships")).not.toContainText("SYN ");
  const link = page.getByTestId("event-source").first();
  if (await link.count()) await expect(link).toHaveAttribute("target", "_blank");
  await page.getByTestId("ship-row").first().locator("[tabindex]").focus(); // hover card
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.getByTestId("ship-row").first().locator("[tabindex]").focus();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${SHOTS}/control-tower-real-${theme}.png`, fullPage: true });
  }
  await page.getByTestId("data-select").selectOption("real:yesterday");
  await expect(page.getByTestId("data-select")).toHaveValue("real:yesterday");
  await page.getByTestId("data-select").selectOption("real:today");
});

test("Data & Models: sources, licences, scenarios", async ({ page }) => {
  await page.goto("/data");
  await expect(page).toHaveTitle(new RegExp(`Data & Models · ${BRAND}`));
  const gfw = page.locator('[data-source="DS-AIS-02"]');
  await expect(gfw).toContainText("NC");
  await expect(page.locator('[data-source="DS-PORT-07"]')).toContainText("Chittagong Port Authority");
  await expect(page.getByText("Cyclone shuts Chattogram + denim mill flood").first()).toBeVisible();
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${SHOTS}/data-models-${theme}.png`, fullPage: true });
  }
});

test("Supplier Network: leaderboard, node drawer and a what-if (C1)", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "cyclone_supplier_delay", url: baseURL! }]);
  await page.goto("/network");
  await expect(page).toHaveTitle(new RegExp(`Supplier Network · ${BRAND}`));
  await expect(page.locator("[data-testid=supply-graph][data-ready=true]")).toBeVisible({ timeout: 30_000 });
  const leaders = page.locator("[data-testid=leaderboard] button");
  await expect(leaders.first()).toContainText("Chattogram");
  await page.waitForTimeout(800);
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SHOTS}/supplier-network-${theme}.png`, fullPage: true });
  }
  await setTheme(page, "light");
  await leaders.filter({ hasText: "Orivell" }).first().click(); // the planted denim single point of failure
  const drawer = page.getByTestId("node-drawer");
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("risk-drivers")).toContainText("Single point of failure");
  await expect(page.getByTestId("tts-ttr")).toContainText("Time to survive");
  await page.locator("[data-testid=whatif-panel] input[name=duration_d]").fill("21");
  await page.locator("[data-testid=whatif-panel] input[name=capacity_pct]").fill("0");
  await page.locator("[data-testid=whatif-panel] input[name=extra_lead_time_d]").fill("0");
  await page.getByTestId("run-whatif").click();
  const result = page.getByTestId("whatif-result");
  await expect(result).toContainText("Orders late", { timeout: 15_000 });
  await expect(result).toContainText("Qualify a second source");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${SHOTS}/supplier-network-whatif.png`, fullPage: true });
  await page.getByTestId("view-map").click();
  await expect(page.getByTestId("supply-map")).toHaveAttribute("data-idle", "true", { timeout: 30_000 });
});

test("Disruption Radar: one grounded event, evidence and a costed recommendation (C2, NX)", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "cyclone_supplier_delay", url: baseURL! }]);
  await page.goto("/radar");
  await expect(page).toHaveTitle(new RegExp(`Disruption Radar · ${BRAND}`));
  const feed = page.getByTestId("event-feed");
  const cyclone = feed.locator("button", { hasText: "Cyclone SYN-01" }).first();
  await expect(cyclone).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("event-map")).toHaveAttribute("data-idle", "true", { timeout: 30_000 });
  await cyclone.click();
  const drawer = page.getByTestId("event-drawer");
  await expect(drawer).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("evidence").locator("mark").first()).toBeVisible();
  // Late orders blocked at the shut port: the costed action is a reroute (C1 cause "gateway").
  await expect(page.getByTestId("reroute-rec").first()).toContainText("Expected benefit");
  // NX-AC03: the news is corroborated by the hazard feed (evidence fusion).
  await expect(page.getByTestId("corroboration")).toContainText("hazard");
  // NX-AC04 / golden path step 5: the cyclone forecast (hazard feed) gets ranked actions.
  await page.getByRole("link", { name: "Feeds", exact: true }).click();
  await expect(page).toHaveURL(/source=feeds/);
  await feed.locator("button", { hasText: "Tropical Cyclone SYN-01" }).first().click();
  // The goods are made but the port is shut: Nexus reroutes the exports (C1 cause "gateway").
  await expect(page.getByTestId("reroute-rec").first()).toContainText("Expected value", { timeout: 15_000 });
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(400);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${SHOTS}/disruption-radar-${theme}.png`, fullPage: true });
  }
});

test("Route Planner: Pareto plans, on-time odds and a departure strip (C3)", async ({ page }) => {
  await page.goto("/routes");
  await expect(page).toHaveTitle(new RegExp(`Route Planner · ${BRAND}`));
  await page.getByTestId("plan-route").click();
  const cards = page.getByTestId("plan-cards").locator("button");
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  expect(await cards.count()).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId("plan-cards")).toContainText("on time");
  await expect(page.getByTestId("departures")).toBeVisible();
  // Traffic under the route: live where Mapbox has it, else C3's model; the source is always named.
  await expect(page.getByTestId("traffic-legend")).toContainText(/Live congestion \(Mapbox\)|Modelled at/);
  await expect(page.getByTestId("route-map")).toHaveAttribute("data-idle", "true", { timeout: 30_000 });
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(400);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${SHOTS}/route-planner-${theme}.png`, fullPage: true });
  }
});

test("Ports & Vessels: queue fan, vessel windows and a vessel's drivers (C4)", async ({ page }) => {
  await page.goto("/ports");
  await expect(page).toHaveTitle(new RegExp(`Ports & Vessels · ${BRAND}`));
  await expect(page.getByTestId("port-kpis")).toContainText("Vessels in port");
  await expect(page.getByTestId("queue-fan").locator("svg path").first()).toBeVisible();
  await expect(page.getByText("Replay").first()).toBeVisible();
  const rows = page.getByTestId("vessel-table").locator("tbody tr");
  expect(await rows.count()).toBeGreaterThan(5);
  const before = await page.getByTestId("snapshot").textContent();
  await page.getByRole("button", { name: "Previous day" }).click();
  await expect(page.getByTestId("snapshot")).not.toHaveText(before ?? "", { timeout: 15_000 });
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(400);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${SHOTS}/ports-vessels-${theme}.png`, fullPage: true });
  }
  await rows.first().click();
  await expect(page.getByTestId("drivers").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("vessel-drawer")).toContainText("How the estimate moved");
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SHOTS}/ports-vessel-drawer.png` });
});

test("Quality Lab: AQL lot board, a failed lot's options and heatmaps (C5)", async ({ page }) => {
  await page.goto("/quality");
  await expect(page).toHaveTitle(new RegExp(`Quality Lab · ${BRAND}`));
  await expect(page.getByTestId("quality-kpis")).toContainText("Rejected");
  const rows = page.getByTestId("lot-board").locator("tbody tr");
  expect(await rows.count()).toBeGreaterThan(5);
  await expect(page.getByTestId("gallery").locator("figure").first()).toBeVisible();
  await expect(page.getByTestId("lines").locator("li").first()).toBeVisible();
  // Screenshots paused: the old files are corrupted on the NTFS drive (docs come later).
  await page.getByLabel("Status").selectOption("rejected");
  await page.getByTestId("lot-board").locator("tbody tr.font-medium").first().click();
  const drawer = page.getByTestId("lot-drawer");
  await expect(drawer.getByTestId("aql")).toContainText("ISO 2859-1");
  await expect(drawer.getByTestId("options").locator("li").nth(1)).toBeVisible();
  await expect(drawer.getByTestId("items").locator("figure").first()).toBeVisible();
});

test("Theme toggle switches and persists", async ({ page }) => {
  await page.goto("/scenarios");
  await setTheme(page, "light");
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("heading", { name: "Scenario Studio", level: 1 })).toBeVisible();
});

test("Scenario Studio: with Nexus vs without (NX-AC05)", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "scenario", value: "cyclone_supplier_delay", url: baseURL! }]);
  await page.goto("/scenarios");
  await expect(page).toHaveTitle(new RegExp(`Scenario Studio · ${BRAND}`));
  const table = page.getByTestId("comparison");
  await expect(table).toBeVisible({ timeout: 15_000 });
  for (const kpi of ["Orders at risk", "OTIF", "CO2e per TEU"]) await expect(table).toContainText(kpi);
  await expect(page.getByTestId("actions")).toContainText("Export via Mongla");
  await expect(page.getByTestId("print")).toBeVisible();
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${SHOTS}/scenario-studio-${theme}.png`, fullPage: true });
  }
});
