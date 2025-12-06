import { test } from '../../../fixtures/base.fixture';
import { StableAudioPage } from '../../../page-objects/services/StableAudioPage';
import { isServiceAvailable } from '../../../utils/wait-helpers';

test.describe('Stable Audio service UI', () => {
  const serviceUrl = process.env.STABLE_AUDIO_URL || 'http://localhost:7873';

  test('loads main page', async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `Stable Audio service not available at ${serviceUrl}`);
    const ui = new StableAudioPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
