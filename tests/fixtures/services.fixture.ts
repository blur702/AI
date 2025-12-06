import { test as base } from './base.fixture';
import { waitForServiceReady } from '../utils/wait-helpers';

export const test = base.extend<{
  servicesHealthy: boolean;
}>({
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
  ]
});
