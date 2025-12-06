import { test } from '../../../fixtures/base.fixture';
import { DiffRhythmPage } from '../../../page-objects/services/DiffRhythmPage';
import { isServiceAvailable } from '../../../utils/wait-helpers';

test.describe('DiffRhythm service UI', () => {
  const serviceUrl = process.env.DIFFRHYTHM_URL || 'http://localhost:7871';

  test('loads main page', async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `DiffRhythm service not available at ${serviceUrl}`);
    const ui = new DiffRhythmPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
