import { test } from '../../../fixtures/base.fixture';
import { YuEPage } from '../../../page-objects/services/YuEPage';
import { isServiceAvailable } from '../../../utils/wait-helpers';

test.describe('YuE service UI', () => {
  const serviceUrl = process.env.YUE_URL || 'http://localhost:7870';

  test('loads main page', async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `YuE service not available at ${serviceUrl}`);
    const ui = new YuEPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
