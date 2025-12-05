import { test } from '../../../fixtures/services.fixture';
import { Wan2GPPage } from '../../../page-objects/services/Wan2GPPage';

test.describe('Wan2GP service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new Wan2GPPage(page);
    await ui.goto(process.env.WAN2GP_URL || 'http://localhost:9000');
    await ui.waitForPageLoad();
  });
});
