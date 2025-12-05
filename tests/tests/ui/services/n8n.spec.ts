import { test } from '../../../fixtures/services.fixture';
import { N8NPage } from '../../../page-objects/services/N8NPage';

test.describe('N8N service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new N8NPage(page);
    await ui.goto(process.env.N8N_URL || 'http://localhost:5678');
    await ui.waitForPageLoad();
  });
});
