import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** Polish checklist (05 §10): no serious or critical accessibility violations on any page. */
const PAGES = ["/", "/ports", "/network", "/radar", "/routes", "/quality", "/scenarios", "/data", "/welcome"];

for (const scheme of ["light", "dark"] as const) for (const path of PAGES) {
  test(`a11y ${scheme} ${path}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const bad = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    console.log(`${scheme} ${path}: ${bad.map((v) => `${v.id}(${v.nodes.length})`).join(", ") || "clean"}`);
    expect(bad, bad.map((v) => `${v.id}: ${v.help}`).join("\n")).toEqual([]);
  });
}
