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

test("Theme toggle switches and persists", async ({ page }) => {
  await page.goto("/ports");
  await setTheme(page, "light");
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByText("Arrives in M6 (C4)")).toBeVisible();
});
