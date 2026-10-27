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
  await expect(page.locator('[data-kpi="co2e_week"]')).toContainText("M5");
  await waitForVessels(page);
  await expect(page.getByTestId("alert-feed")).toContainText("SYN-01");
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await mapIdle(page);
    await page.screenshot({ path: `${SHOTS}/control-tower-${theme}.png`, fullPage: true });
  }
});

test("Scenario switch: real data only shows the replay badge", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Scenario").selectOption("");
  await expect(page.locator('[data-kpi="vessels_at_anchorage"] [data-mode]')).toHaveAttribute("data-mode", "replay", {
    timeout: 15_000,
  });
  await page.getByLabel("Scenario").selectOption("cyclone_supplier_delay");
  await expect(page.locator('[data-kpi="vessels_at_anchorage"] [data-mode]')).toHaveAttribute("data-mode", "synthetic", {
    timeout: 15_000,
  });
});

test("Data & Models: sources, licences, scenarios", async ({ page }) => {
  await page.goto("/data");
  await expect(page).toHaveTitle(new RegExp(`Data & Models · ${BRAND}`));
  const gfw = page.locator('[data-source="DS-AIS-02"]');
  await expect(gfw).toContainText("NC");
  await expect(page.locator('[data-source="DS-PORT-07"]')).toContainText("Chittagong Port Authority");
  await expect(page.getByText("Cyclone SYN-01 + Fabric Mill X delay")).toBeVisible();
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

test("Theme toggle switches and persists", async ({ page }) => {
  await page.goto("/ports");
  await setTheme(page, "light");
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByText("Arrives in M6 (C4)")).toBeVisible();
});
