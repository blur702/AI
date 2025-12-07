import { test, expect } from '../../fixtures/base.fixture';
import { waitForServiceReady } from '../../utils/wait-helpers';

/**
 * Helper to normalize URL by removing trailing slash
 */
function normalizeBaseURL(url: string): string {
  return url.replace(/\/$/, '');
}

test.describe.parallel('Smoke tests', () => {
  test('Dashboard backend is responding', async ({ dashboardAPI }) => {
    const vram = await dashboardAPI.getVRAMStatus();
    expect(vram.gpu).toBeTruthy();
  });

  test('API Gateway health endpoint is responding', async ({ gatewayAPI }) => {
    try {
      const health = await gatewayAPI.getHealth();
      expect(health.success).toBe(true);
    } catch (error: any) {
      // Skip test if gateway is not running (ECONNREFUSED)
      if (error.code === 'ECONNREFUSED' || error.message?.includes('ECONNREFUSED')) {
        test.skip(true, 'API Gateway is not running (port 1301)');
        return;
      }
      throw error;
    }
  });

  test('Core services respond with 200', async () => {
    // Only check core services that should always be running for tests
    // Dashboard is required, others are optional
    const dashboardBase = normalizeBaseURL(process.env.DASHBOARD_API_URL || 'http://localhost');
    const dashboardUrl = dashboardBase + '/api/vram/status';

    // Dashboard must be available
    await waitForServiceReady(dashboardUrl, 10_000);

    // Check optional services and track which are available
    const gatewayBase = normalizeBaseURL(process.env.GATEWAY_API_URL || 'http://localhost:1301');
    const optionalServices = [
      { name: 'API Gateway', url: gatewayBase + '/health' },
      { name: 'Ollama', url: process.env.OLLAMA_URL || 'http://localhost:11434' }
    ];

    const results: string[] = [];
    for (const service of optionalServices) {
      try {
        await waitForServiceReady(service.url, 5_000);
        results.push(`✓ ${service.name}`);
      } catch {
        results.push(`○ ${service.name} (offline)`);
      }
    }
    console.log('Service availability:', results.join(', '));
  });

  // Skip: This test requires all AI services to be running
  test.skip('All configured services respond with 200', async () => {
    const serviceUrls = [
      process.env.DASHBOARD_API_URL,
      process.env.GATEWAY_API_URL,
      process.env.OPEN_WEBUI_URL,
      process.env.COMFYUI_URL,
      process.env.OLLAMA_URL,
      process.env.WAN2GP_URL,
      process.env.YUE_URL,
      process.env.DIFFRHYTHM_URL,
      process.env.MUSICGEN_URL,
      process.env.STABLE_AUDIO_URL,
      process.env.ALLTALK_URL,
      process.env.N8N_URL
    ].filter((u): u is string => !!u);

    await Promise.all(serviceUrls.map((url) => waitForServiceReady(url, 30_000)));
  });
});
