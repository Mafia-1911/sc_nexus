import { writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

/**
 * The golden path (01-product §5, NX-AC01), walked in order with the network cut: every request
 * that is not to this machine is aborted and recorded. Run `make golden` first (offline worker,
 * fresh decisions). Writes step timings and the blocked hosts to docs/golden-path.json.
 */
const BRAND = process.env.CPORTAL_BRAND_NAME ?? "ShipperFast";
const HERO = "cyclone_supplier_delay";

test("Golden path: one connected story, offline, under 7 minutes", async ({ page, baseURL }) => {
  test.setTimeout(7 * 60_000);
  const blocked = new Set<string>();
  await page.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host === "127.0.0.1" || host === "localhost") return route.continue();
    blocked.add(host);
    return route.abort();
  });
  await page.context().addCookies([{ name: "scenario", value: HERO, url: baseURL! }]);
  const steps: { step: string; ms: number }[] = [];
  const t0 = Date.now();
  async function step(name: string, body: (p: Page) => Promise<void>) {
    const start = Date.now();
    await test.step(name, () => body(page));
    steps.push({ step: name, ms: Date.now() - start });
  }

  await step("1 Control Tower: anchorage, KPIs, the cyclone alert", async (p) => {
    await p.goto("/");
    await expect(p).toHaveTitle(new RegExp(`Control Tower · ${BRAND}`));
    await expect(p.locator("[data-kpi]")).toHaveCount(5);
    await expect(p.getByTestId("vessel-count")).toHaveText(/^[1-9]\d* vessels$/, { timeout: 30_000 });
    await expect(p.getByTestId("alert-feed")).toContainText("SYN-01");
    await expect(p.getByTestId("ship-row").first()).toBeVisible(); // ships at Chattogram
  });

  await step("2 Disruption Radar: news + hazard feed → one corroborated event", async (p) => {
    await p.goto("/radar");
    const news = p.getByTestId("event-feed").locator("button", { hasText: "Chattogram port suspends" }).first();
    await news.click();
    await expect(p.getByTestId("event-drawer")).toContainText("fused", { timeout: 15_000 });
    await expect(p.getByTestId("corroboration")).toContainText("hazard");
  });

  await step("3 Ports & Vessels: congestion forecast and the drivers", async (p) => {
    await p.goto("/ports");
    await expect(p.getByTestId("port-kpis")).toContainText("Vessels in port", { timeout: 15_000 });
    await expect(p.getByTestId("queue-fan").locator("svg path").first()).toBeVisible();
    await p.getByTestId("vessel-table").locator("tbody tr").first().click();
    await expect(p.getByTestId("drivers").locator("li").first()).toBeVisible();
  });

  await step("4 Supplier Network: Chattogram, the single point of failure", async (p) => {
    await p.goto("/network");
    await expect(p.locator("[data-testid=supply-graph][data-ready=true]")).toBeVisible({ timeout: 30_000 });
    await expect(p.locator("[data-testid=leaderboard] button").first()).toContainText("Chattogram");
  });

  await step("5 Recommendation: export via Mongla, accepted", async (p) => {
    await p.goto("/radar?source=feeds");
    await p.getByTestId("event-feed").locator("button", { hasText: "Tropical Cyclone SYN-01" }).first().click();
    const rec = p.getByTestId("reroute-rec").first();
    await expect(rec).toContainText("Expected value", { timeout: 15_000 });
    await expect(rec).toContainText("Confidence");
    await rec.getByRole("button", { name: "Accept" }).click();
    await expect(rec).toContainText("accepted");
  });

  await step("6 Route Planner: Pareto options after discharge", async (p) => {
    await p.goto("/routes");
    await p.getByTestId("plan-route").click();
    await expect(p.getByTestId("plan-cards")).toContainText("on time", { timeout: 30_000 });
  });

  await step("7 Quality Lab: a failed lot and its options", async (p) => {
    await p.goto("/quality");
    await expect(p.getByTestId("quality-kpis")).toContainText("Rejected", { timeout: 15_000 });
    await p.getByLabel("Status").selectOption("rejected");
    await p.getByTestId("lot-board").locator("tbody tr.font-medium").first().click();
    await expect(p.getByTestId("lot-drawer").getByTestId("options").locator("li").first()).toBeVisible();
  });

  await step("8 Scenario Studio: with Nexus vs without", async (p) => {
    await p.goto("/scenarios");
    await expect(p.getByTestId("comparison")).toContainText("OTIF", { timeout: 15_000 });
    await expect(p.getByTestId("actions")).toContainText("Export via Mongla");
  });

  const total = Date.now() - t0;
  writeFileSync(
    "../../docs/golden-path.json",
    JSON.stringify(
      { scenario: HERO, total_ms: total, steps, blocked_hosts: [...blocked].sort(), run_at: new Date().toISOString() },
      null,
      1,
    ) + "\n",
  );
  expect(total).toBeLessThan(7 * 60_000);
});
