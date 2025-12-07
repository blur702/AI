import type { Page } from "@playwright/test";

/**
 * Wait for the React dashboard to fully render:
 * - Navigate to root
 * - Wait for DOMContentLoaded
 * - Wait for React to mount content into #root
 * - Wait for at least one .card element to appear
 */
export async function waitForDashboardReady(page: Page): Promise<void> {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");

  await page.waitForFunction(
    () => {
      const root = document.getElementById("root");
      return root && root.children.length > 0;
    },
    { timeout: 15000 },
  );

  await page.waitForSelector(".card", { timeout: 10000 });
}
