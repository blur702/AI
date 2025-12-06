import { test, expect } from '../../../fixtures/base.fixture';
import { DashboardPage } from '../../../page-objects/dashboard/DashboardPage';

test.describe('Dashboard UI display', () => {
  test('shows service cards and status indicators', async ({ page, screenshotManager }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(process.env.BASE_URL || 'http://localhost:8080');

    await dashboard.waitForPageLoad();

    // The dashboard uses .card class for service cards
    const serviceCardSelector = '.card';
    await dashboard.waitForSelector(serviceCardSelector);

    const cardsCount = await page.locator(serviceCardSelector).count();
    expect(cardsCount).toBeGreaterThan(0);

    // Status indicators use .status class
    const statusIndicators = page.locator('.card .status');
    expect(await statusIndicators.count()).toBeGreaterThan(0);

    // IP info section
    const ipDisplay = page.locator('.ip-info');
    expect(await ipDisplay.count()).toBeGreaterThan(0);

    // Basic responsive layout check via viewport resize
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.setViewportSize({ width: 414, height: 896 });

    await screenshotManager.captureFullPage(page, 'dashboard-display');
  });
});
