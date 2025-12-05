import { test } from '../../../fixtures/services.fixture';
import { DiffRhythmPage } from '../../../page-objects/services/DiffRhythmPage';

test.describe('DiffRhythm service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new DiffRhythmPage(page);
    await ui.goto(process.env.DIFFRHYTHM_URL || 'http://localhost:9002');
    await ui.waitForPageLoad();
  });
});
