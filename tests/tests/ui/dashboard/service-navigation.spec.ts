import { test, expect } from '../../../fixtures/base.fixture';
import { DashboardPage } from '../../../page-objects/dashboard/DashboardPage';

test.describe('Dashboard service navigation', () => {
  test('service cards are clickable (placeholder)', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(process.env.BASE_URL || 'http://localhost/index.html');

    await dashboard.waitForSelector('.service-card');
    const firstCard = page.locator('.service-card').first();
    await firstCard.click();
    expect(await firstCard.isVisible()).toBe(true);
  });
});
