import { test as base, expect } from './base.fixture';
import { waitForServiceReady } from '../utils/wait-helpers';
import { isVPSEnvironment, ServiceIds, ServiceId } from '../utils/vps-helpers';

/**
 * Extended test fixture with service-specific helpers.
 *
 * Provides fixtures for:
 * - Service health checking
 * - Individual service enablers (withOllama, withComfyUI, etc.)
 * - Automatic service startup in VPS mode
 */
export const test = base.extend<{
  servicesHealthy: boolean;
  withOllama: void;
  withComfyUI: void;
  withAllTalk: void;
  withWan2GP: void;
  withYuE: void;
  withDiffRhythm: void;
  withMusicGen: void;
  withStableAudio: void;
  withN8N: void;
  withWeaviate: void;
}>({
  /**
   * Check if all configured services are healthy
   */
  servicesHealthy: [
    async ({}, use) => {
      const serviceUrls = [
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

      let healthy = true;
      try {
        await Promise.all(serviceUrls.map((url) => waitForServiceReady(url, 5_000)));
      } catch {
        healthy = false;
      }

      await use(healthy);
    },
    { auto: false }
  ],

  /**
   * Ensure Ollama is running before the test
   */
  withOllama: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.OLLAMA);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure ComfyUI is running before the test
   */
  withComfyUI: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.COMFYUI);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure AllTalk TTS is running before the test
   */
  withAllTalk: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.ALLTALK);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure Wan2GP Video is running before the test
   */
  withWan2GP: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.WAN2GP);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure YuE Music is running before the test
   */
  withYuE: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.YUE);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure DiffRhythm is running before the test
   */
  withDiffRhythm: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.DIFFRHYTHM);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure MusicGen is running before the test
   */
  withMusicGen: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.MUSICGEN);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure Stable Audio is running before the test
   */
  withStableAudio: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.STABLE_AUDIO);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure N8N is running before the test
   */
  withN8N: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.N8N);
      await use();
    },
    { auto: false }
  ],

  /**
   * Ensure Weaviate is running before the test
   */
  withWeaviate: [
    async ({ ensureServices }, use) => {
      await ensureServices.ensureService(ServiceIds.WEAVIATE);
      await use();
    },
    { auto: false }
  ]
});

export { expect };

/**
 * Helper to create a test that requires specific services
 *
 * Usage:
 *   test.describe('Image Generation', () => {
 *     requireServices([ServiceIds.COMFYUI, ServiceIds.OLLAMA]);
 *
 *     test('should generate image', async ({ dashboardAPI }) => {
 *       // Test with services guaranteed to be running
 *     });
 *   });
 */
export function requireServices(services: ServiceId[]) {
  test.beforeAll(async ({ ensureServices }) => {
    if (isVPSEnvironment()) {
      console.log(`[Services] Ensuring services: ${services.join(', ')}`);
      await ensureServices.ensureServices(services);
    }
  });
}

/**
 * Skip test if required services are not available
 *
 * Usage:
 *   test('should generate image', async ({ dashboardAPI }) => {
 *     await skipIfServicesUnavailable(dashboardAPI, [ServiceIds.COMFYUI]);
 *     // Test with services
 *   });
 */
export async function skipIfServicesUnavailable(
  dashboardAPI: InstanceType<typeof import('../api-clients/DashboardAPIClient').DashboardAPIClient>,
  requiredServices: ServiceId[]
): Promise<void> {
  for (const serviceId of requiredServices) {
    try {
      const isRunning = await dashboardAPI.isServiceRunning(serviceId);
      if (!isRunning) {
        test.skip(true, `Service '${serviceId}' is not running`);
      }
    } catch (error) {
      test.skip(true, `Could not check service '${serviceId}': ${error}`);
    }
  }
}
