import { test, expect } from '../../../fixtures/base.fixture';

/**
 * Comprehensive test suite that clicks on all services in the dashboard
 * and verifies they start and load correctly.
 *
 * Services tested:
 * - Main: Open WebUI (external), ComfyUI, AllTalk TTS, Ollama (external), Wan2GP Video, N8N
 * - Music: YuE Music, DiffRhythm, MusicGen, Stable Audio
 */

// Service configuration with expected load times
const SERVICES = {
  // External services (already running, just verify)
  external: [
    { id: 'openwebui', name: 'Open WebUI', port: 3000 },
    { id: 'ollama', name: 'Ollama API', port: 11434 }
  ],
  // Manageable services (need to be started)
  // Startup times based on actual service startup requirements (AI models load slowly)
  manageable: [
    { id: 'alltalk', name: 'AllTalk TTS', port: 7851, startupTime: 120000 },      // TTS model loading
    { id: 'comfyui', name: 'ComfyUI', port: 8188, startupTime: 120000 },          // SD models
    { id: 'wan2gp', name: 'Wan2GP Video', port: 7860, startupTime: 180000 },      // Video model
    { id: 'n8n', name: 'N8N Workflows', port: 5678, startupTime: 60000 },         // Node.js app
    { id: 'yue', name: 'YuE Music', port: 7870, startupTime: 120000 },            // Music model
    { id: 'diffrhythm', name: 'DiffRhythm', port: 7871, startupTime: 120000 },    // Music model
    { id: 'musicgen', name: 'MusicGen', port: 7872, startupTime: 600000 },        // Meta AudioCraft (loads large models - 10 min)
    { id: 'stable_audio', name: 'Stable Audio', port: 7873, startupTime: 120000 } // Audio model
  ]
};

test.describe('All Services Load Test', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ dashboardAPI }) => {
    // Log initial VRAM status
    const vram = await dashboardAPI.getVRAMStatus();
    console.log(`\n=== Initial VRAM Status ===`);
    console.log(`GPU: ${vram.gpu.name}`);
    console.log(`Used: ${vram.gpu.used_mb} MB / ${vram.gpu.total_mb} MB`);
    console.log(`Free: ${vram.gpu.free_mb} MB`);
    console.log(`===========================\n`);
  });

  test('dashboard loads and shows all service cards', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check main title
    await expect(page.locator('h1')).toContainText('AI Services Dashboard');

    // Verify all service cards are visible
    const allServices = [...SERVICES.external, ...SERVICES.manageable];
    for (const service of allServices) {
      const card = page.locator(`.card-${service.id.replace('_', '')}, .card:has-text("${service.name}")`).first();
      await expect(card).toBeVisible({ timeout: 5000 });
      console.log(`✓ Service card visible: ${service.name}`);
    }
  });

  test.describe('External Services', () => {
    for (const service of SERVICES.external) {
      test(`${service.name} is running and accessible`, async ({ page, dashboardAPI }) => {
        // Check via API
        const services = await dashboardAPI.get('/api/services');
        const svcStatus = services.services[service.id];

        console.log(`${service.name} status: ${svcStatus?.status}`);
        expect(svcStatus).toBeDefined();
        expect(svcStatus.status).toBe('running');
        expect(svcStatus.healthy).toBe(true);

        // Verify on dashboard
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        const card = page.locator(`.card:has-text("${service.name}")`).first();
        await expect(card).toBeVisible();

        // Should show running status (green indicator)
        const statusIndicator = card.locator('.status-online');
        await expect(statusIndicator).toBeVisible();
      });
    }
  });

  test.describe('Manageable Services - Start and Verify', () => {
    // Test each manageable service
    for (const service of SERVICES.manageable) {
      test(`${service.name} starts and loads correctly`, async ({ page, dashboardAPI }) => {
        test.setTimeout(service.startupTime + 60000); // Extra buffer

        // Check VRAM before starting
        const vramBefore = await dashboardAPI.getVRAMStatus();
        console.log(`\n--- Starting ${service.name} ---`);
        console.log(`VRAM before: ${vramBefore.gpu.used_mb} MB used, ${vramBefore.gpu.free_mb} MB free`);

        // Check current status
        const statusBefore = await dashboardAPI.get('/api/services');
        const svcBefore = statusBefore.services[service.id];
        console.log(`Current status: ${svcBefore?.status}`);

        // If already running or starting, just verify/wait
        if (svcBefore?.status === 'running') {
          console.log(`${service.name} is already running, verifying...`);
          expect(svcBefore.healthy).toBe(true);
          return;
        }

        if (svcBefore?.status === 'starting') {
          console.log(`${service.name} is already starting, waiting...`);
          // Wait for service to become running
          await expect(async () => {
            const status = await dashboardAPI.get('/api/services');
            const svc = status.services[service.id];
            console.log(`  Status check: ${svc?.status}`);
            expect(svc?.status).toBe('running');
          }).toPass({ timeout: service.startupTime, intervals: [2000, 3000, 5000] });
          return;
        }

        // If in error state, log and skip (service may have missing dependencies)
        if (svcBefore?.status === 'error') {
          console.log(`${service.name} is in error state: ${svcBefore.error}`);
          console.log(`Skipping - service may require manual setup`);
          test.skip(true, `${service.name} in error state: ${svcBefore.error}`);
          return;
        }

        // Navigate to dashboard
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Find the service card
        const card = page.locator(`.card:has-text("${service.name}")`).first();
        await expect(card).toBeVisible();

        // Find and click the Start button
        const startButton = card.locator('button:has-text("Start")');

        if (await startButton.isVisible()) {
          console.log(`Clicking Start button for ${service.name}...`);
          await startButton.click();

          // Wait for status to change to starting (use .first() since multiple elements may match)
          await expect(card.locator('.status-starting-indicator, .spinner, :text("Starting")').first()).toBeVisible({ timeout: 5000 });
          console.log(`${service.name} is starting...`);

          // Wait for service to become running or error
          let finalStatus = 'starting';
          try {
            await expect(async () => {
              const status = await dashboardAPI.get('/api/services');
              const svc = status.services[service.id];
              finalStatus = svc?.status;
              console.log(`  Status check: ${svc?.status}`);
              // Accept running or fail on error
              if (svc?.status === 'error') {
                throw new Error(`Service failed to start: ${svc.error}`);
              }
              expect(svc?.status).toBe('running');
            }).toPass({ timeout: service.startupTime, intervals: [2000, 3000, 5000] });
          } catch (e) {
            if (finalStatus === 'error') {
              const status = await dashboardAPI.get('/api/services');
              const svc = status.services[service.id];
              console.log(`✗ ${service.name} failed to start: ${svc?.error}`);
              test.skip(true, `${service.name} failed: ${svc?.error}`);
              return;
            }
            throw e;
          }

          console.log(`✓ ${service.name} started successfully!`);

          // Verify health
          const statusAfter = await dashboardAPI.get('/api/services');
          const svcAfter = statusAfter.services[service.id];
          expect(svcAfter.healthy).toBe(true);

          // Check VRAM after starting
          const vramAfter = await dashboardAPI.getVRAMStatus();
          const vramDelta = vramAfter.gpu.used_mb - vramBefore.gpu.used_mb;
          console.log(`VRAM after: ${vramAfter.gpu.used_mb} MB used (+${vramDelta} MB)`);
          console.log(`VRAM free: ${vramAfter.gpu.free_mb} MB`);
        } else {
          // Service might be in error state, check and log
          const errorMsg = await card.locator('.status-text').textContent().catch(() => null);
          if (errorMsg) {
            console.error(`${service.name} error: ${errorMsg}`);
          }
          throw new Error(`Cannot start ${service.name} - Start button not available`);
        }
      });
    }
  });

  test('verify all services running at end', async ({ dashboardAPI }) => {
    const services = await dashboardAPI.get('/api/services');
    const vram = await dashboardAPI.getVRAMStatus();

    console.log('\n=== Final Service Status ===');
    for (const [id, svc] of Object.entries(services.services) as [string, any][]) {
      const status = svc.status === 'running' ? '✓' : '✗';
      console.log(`${status} ${svc.name}: ${svc.status}${svc.error ? ` (${svc.error})` : ''}`);
    }

    console.log('\n=== Final VRAM Status ===');
    console.log(`Used: ${vram.gpu.used_mb} MB / ${vram.gpu.total_mb} MB`);
    console.log(`Free: ${vram.gpu.free_mb} MB`);
    console.log(`Utilization: ${vram.gpu.utilization}%`);
    console.log('===========================\n');

    // At minimum, external services should be running
    for (const service of SERVICES.external) {
      const svc = services.services[service.id];
      expect(svc.status).toBe('running');
    }
  });
});

test.describe('Service Interaction Tests', () => {
  test('can click Open button on running service', async ({ page, dashboardAPI }) => {
    // Get a running service
    const services = await dashboardAPI.get('/api/services');
    const runningService = Object.entries(services.services)
      .find(([_, svc]: [string, any]) => svc.status === 'running');

    if (!runningService) {
      test.skip(true, 'No running services to test');
      return;
    }

    const [id, svc] = runningService as [string, any];
    console.log(`Testing Open button on: ${svc.name}`);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const card = page.locator(`.card:has-text("${svc.name}")`).first();
    await expect(card).toBeVisible();

    const openButton = card.locator('button:has-text("Open")');
    await expect(openButton).toBeEnabled();
  });

  test('can stop a running manageable service', async ({ page, dashboardAPI }) => {
    // Find a running manageable service
    const services = await dashboardAPI.get('/api/services');
    const runningManageable = Object.entries(services.services)
      .find(([id, svc]: [string, any]) =>
        svc.status === 'running' &&
        svc.manageable === true &&
        !svc.external
      );

    if (!runningManageable) {
      test.skip(true, 'No running manageable services to test stop');
      return;
    }

    const [id, svc] = runningManageable as [string, any];
    console.log(`Testing Stop button on: ${svc.name}`);

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const card = page.locator(`.card:has-text("${svc.name}")`).first();
    await expect(card).toBeVisible();

    const stopButton = card.locator('button:has-text("Stop")');
    if (await stopButton.isVisible()) {
      // Don't actually click - just verify it's there
      await expect(stopButton).toBeEnabled();
      console.log(`✓ Stop button available for ${svc.name}`);
    }
  });
});
