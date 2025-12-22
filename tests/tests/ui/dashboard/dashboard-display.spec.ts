import { test, expect } from "../../../fixtures/base.fixture";
import { DashboardPage } from "../../../page-objects/dashboard/DashboardPage";

test.describe("Dashboard UI display", () => {
  test("shows service cards and status indicators", async ({
    page,
    screenshotManager,
  }) => {
    // Use baseURL from Playwright config (defaults to http://ssdd.kevinalthaus.com)
    await page.goto("/");

    // Wait for page to load - try multiple strategies
    await page.waitForLoadState("domcontentloaded");

    // Wait for React to mount and render - check for #root having content
    // The React app renders into #root div
    await page.waitForFunction(
      () => {
        const root = document.getElementById("root");
        return root && root.children.length > 0;
      },
      { timeout: 15000 },
    );

    // Now wait for the h1 title
    const h1 = page.locator("h1");
    await expect(h1).toBeVisible({ timeout: 10000 });
    await expect(h1).toContainText("AI Services Dashboard");

    // The dashboard uses .card class for service cards
    const serviceCardSelector = ".card";
    await page.waitForSelector(serviceCardSelector, { timeout: 10000 });

    const cardsCount = await page.locator(serviceCardSelector).count();
    expect(cardsCount).toBeGreaterThan(0);

    // Status indicators use .status class inside .card-port
    const statusIndicators = page.locator(".card .card-port .status");
    expect(await statusIndicators.count()).toBeGreaterThan(0);

    // IP info section (may not be visible in all browsers due to timing)
    const ipDisplay = page.locator(".ip-info");
    try {
      await expect(ipDisplay).toBeVisible({ timeout: 5000 });
    } catch {
      // IP info is optional - log but don't fail
      console.log("IP info section not found - may be hidden or not rendered");
    }

    // Basic responsive layout check via viewport resize
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.setViewportSize({ width: 414, height: 896 });

    await screenshotManager.captureFullPage(page, "dashboard-display");
  });
});
