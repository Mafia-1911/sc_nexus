import { expect, test } from "@playwright/test";

/** A-111: every page shows one data source: real data never shows a SYNTHETIC badge, and a
 *  scenario never shows real (live/replay) rows. */
const PAGES = ["/", "/ports", "/network", "/radar", "/routes", "/quality", "/scenarios"];
const MODES = [
  { scenario: "", forbidden: "synthetic" },
  { scenario: "cyclone_supplier_delay", forbidden: "live" },
];

for (const { scenario, forbidden } of MODES) {
  for (const path of PAGES) {
    test(`${path} follows ${scenario || "real data"}`, async ({ page, context, baseURL }) => {
      await context.addCookies([{ name: "scenario", value: scenario, url: baseURL! }]);
      const res = await page.goto(path);
      expect(res?.status()).toBeLessThan(500);
      await page.waitForLoadState("networkidle");
      const modes = await page.locator("[data-mode]").evaluateAll((els) =>
        els.map((e) => e.getAttribute("data-mode")),
      );
      expect(modes, `${path}: badges ${modes.join(",")}`).not.toContain(forbidden);
      if (scenario) expect(modes, `${path}: badges ${modes.join(",")}`).not.toContain("replay");
    });
  }
}
