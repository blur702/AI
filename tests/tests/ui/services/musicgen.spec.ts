import { test } from '../../../fixtures/services.fixture';
import { MusicGenPage } from '../../../page-objects/services/MusicGenPage';

test.describe('MusicGen service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new MusicGenPage(page);
    await ui.goto(process.env.MUSICGEN_URL || 'http://localhost:9003');
    await ui.waitForPageLoad();
  });
});
