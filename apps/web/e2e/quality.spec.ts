import { expect, type Page, test } from "@playwright/test";

const SHOTS = "../../docs/screenshots";
const BRAND = process.env.CPORTAL_BRAND_NAME ?? "ShipperFast";

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem("theme", t);
    window.dispatchEvent(new CustomEvent("themechange", { detail: t }));
  }, theme);
}

test.describe("Quality Lab: Universal Quality AI (Capability C5)", () => {
  test("Zero-shot visual inspection with real WinCLIP model", async ({ page }) => {
    test.setTimeout(120_000);

    // 1. Visit Quality Lab page
    await page.goto("/quality");
    await expect(page).toHaveTitle(new RegExp(`Quality Lab · ${BRAND}`));
    await expect(page.locator("h1")).toContainText("Quality Lab");

    // 2. Initial state: Zipper Defect (Broken Teeth) preset is loaded
    await expect(page.getByText("Universal Quality AI")).toBeVisible();
    await expect(page.getByText("Zipper Defect")).toBeVisible();

    // 3. Trigger inspection with real WinCLIP inference
    const inspectButton = page.getByRole("button", { name: /Run Zero-Shot Quality Inspection/i });
    await expect(inspectButton).toBeVisible();
    await inspectButton.click();

    // 4. Wait for real model inference to complete (up to 30s on CPU)
    await expect(page.getByText(/POSSIBLE ANOMALY — Flagged for QA Review/i)).toBeVisible({
      timeout: 45_000,
    });

    // 5. Verify metrics and localization heatmap
    await expect(page.getByText("Anomaly Score")).toBeVisible();
    await expect(page.getByText("Threshold", { exact: true })).toBeVisible();
    await expect(page.getByText("Defect Localization (JET Colormap)")).toBeVisible();

    // 6. Capture light and dark mode screenshots
    for (const theme of ["light", "dark"] as const) {
      await setTheme(page, theme);
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${SHOTS}/quality-lab-${theme}.png`, fullPage: true });
    }

    // 7. Test switching to Capsule and inspecting Flawless sample
    await page.getByRole("button", { name: /Capsule Flawless/i }).click();
    await expect(page.getByRole("button", { name: /Capsule/i }).first()).toBeVisible();

    // Run inspection on capsule nominal
    await inspectButton.click();
    await expect(page.getByText(/NOMINAL — No Significant Anomaly Detected/i)).toBeVisible({
      timeout: 45_000,
    });
  });
});
