import { test } from '../../../fixtures/services.fixture';
import { AllTalkPage } from '../../../page-objects/services/AllTalkPage';

test.describe('AllTalk service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new AllTalkPage(page);
    await ui.goto(process.env.ALLTALK_URL || 'http://localhost:9005');
    await ui.waitForPageLoad();
  });
});
