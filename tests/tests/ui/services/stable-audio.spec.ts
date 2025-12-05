import { test } from '../../../fixtures/services.fixture';
import { StableAudioPage } from '../../../page-objects/services/StableAudioPage';

test.describe('Stable Audio service UI', () => {
  test('loads main page', async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, 'Services not marked healthy');
    const ui = new StableAudioPage(page);
    await ui.goto(process.env.STABLE_AUDIO_URL || 'http://localhost:9004');
    await ui.waitForPageLoad();
  });
});
