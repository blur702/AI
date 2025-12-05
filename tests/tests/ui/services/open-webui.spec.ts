import { test } from '../../../fixtures/services.fixture';
import { OpenWebUIPage } from '../../../page-objects/services/OpenWebUIPage';

test.describe('Open WebUI service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new OpenWebUIPage(page);
    await ui.goto(process.env.OPEN_WEBUI_URL || 'http://localhost:3000');
    await ui.waitForPageLoad();
  });
});
