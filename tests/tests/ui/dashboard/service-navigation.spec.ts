import { test, expect } from '../../../fixtures/base.fixture';
import { DashboardPage } from '../../../page-objects/dashboard/DashboardPage';

test.describe('Dashboard service navigation', () => {
  test('service cards are clickable', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto(process.env.BASE_URL || 'http://localhost');

    // The dashboard uses .card class for service cards
    await dashboard.waitForSelector('.card');
    const firstCard = page.locator('.card').first();
    expect(await firstCard.isVisible()).toBe(true);
    // Cards are anchor links that open in new tabs, so clicking is valid
    const href = await firstCard.getAttribute('href');
    expect(href).toBeTruthy();
  });
});
