import { test } from '../../../fixtures/services.fixture';
import { YuEPage } from '../../../page-objects/services/YuEPage';

test.describe('YuE service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new YuEPage(page);
    await ui.goto(process.env.YUE_URL || 'http://localhost:9001');
    await ui.waitForPageLoad();
  });
});
