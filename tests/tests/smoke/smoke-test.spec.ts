import { test, expect } from '../../fixtures/base.fixture';
import { waitForServiceReady } from '../../utils/wait-helpers';

test.describe.parallel('Smoke tests', () => {
  test('Dashboard backend is responding', async ({ dashboardAPI }) => {
    const vram = await dashboardAPI.getVRAMStatus();
    expect(vram.gpu).toBeTruthy();
  });

  test('API Gateway health endpoint is responding', async ({ gatewayAPI }) => {
    const health = await gatewayAPI.getHealth();
    expect(health.success).toBe(true);
  });

  test('Core services respond with 200', async () => {
    // Only check core services that should always be running for tests
    // Use health/status endpoints rather than root URLs since not all services have root handlers
    // Single-port deployment: Dashboard serves frontend + API on port 80
    const coreServiceUrls = [
      (process.env.DASHBOARD_API_URL || 'http://localhost') + '/api/vram/status',
      (process.env.GATEWAY_API_URL || 'http://localhost:1301') + '/health',
      process.env.OLLAMA_URL || 'http://localhost:11434'
    ];

    await Promise.all(coreServiceUrls.map((url) => waitForServiceReady(url, 10_000)));
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
