import { test } from '../../../fixtures/base.fixture';
import { AllTalkPage } from '../../../page-objects/services/AllTalkPage';
import { isServiceAvailable } from '../../../utils/wait-helpers';

test.describe('AllTalk service UI', () => {
  const serviceUrl = process.env.ALLTALK_URL || 'http://localhost:7851';

  test('loads main page', async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `AllTalk service not available at ${serviceUrl}`);
    const ui = new AllTalkPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
