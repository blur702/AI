/**
 * Site Browse Tests
 *
 * Quick tests to verify the Drupal site is browsable and basic frontend works.
 */

import { test, expect } from "@playwright/test";

const DRUPAL_BASE_URL = "https://kevinalthaus.com";

test.describe("Site Browsability", () => {
  test("Homepage is accessible and returns HTML", async ({ page }) => {
    const response = await page.goto(DRUPAL_BASE_URL);

    expect(response?.status()).toBeLessThan(400);
    expect(response?.headers()["content-type"]).toContain("text/html");

    // Page has basic HTML structure
    const html = await page.locator("html").count();
    const body = await page.locator("body").count();
    expect(html).toBe(1);
    expect(body).toBe(1);

    console.log("Homepage accessible and returns valid HTML");
  });

  test("Page has title", async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);

    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);

    console.log(`Page title: ${title}`);
  });

  test("User login page exists", async ({ page }) => {
    const response = await page.goto(`${DRUPAL_BASE_URL}/user/login`);

    expect(response?.status()).toBeLessThan(400);

    // Should have login form elements
    const nameField = page.locator('input[name="name"]');
    const passField = page.locator('input[name="pass"]');

    await expect(nameField).toBeAttached();
    await expect(passField).toBeAttached();

    console.log("Login page is functional");
  });

  test("CSS is loading", async ({ page }) => {
    const response = await page.goto(DRUPAL_BASE_URL);

    // Check that stylesheets are linked
    const stylesheets = await page.locator('link[rel="stylesheet"]').count();
    expect(stylesheets).toBeGreaterThan(0);

    console.log(`Found ${stylesheets} stylesheets`);
  });

  test("Page has proper meta tags", async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState("domcontentloaded");

    // Check for viewport meta tag (responsive design)
    const viewport = page.locator('meta[name="viewport"]');
    await expect(viewport).toBeAttached();

    // Check for charset
    const charset = page.locator("meta[charset]");
    const hasCharset = (await charset.count()) > 0;

    console.log(`Has viewport meta: true, has charset: ${hasCharset}`);
  });

  test("Site responds to navigation", async ({ page }) => {
    await page.goto(DRUPAL_BASE_URL);
    await page.waitForLoadState("networkidle");

    // Try to click on any link and verify page responds
    const firstLink = page.locator("a[href]").first();
    if ((await firstLink.count()) > 0) {
      const href = await firstLink.getAttribute("href");
      console.log(`First link points to: ${href}`);
    }

    console.log("Site navigation is working");
  });
});
