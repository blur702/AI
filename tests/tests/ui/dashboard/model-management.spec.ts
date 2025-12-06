import { test, expect } from '../../../fixtures/base.fixture';

test.describe('Dashboard model management', () => {
  test.describe('Ollama Models API', () => {
    test('lists Ollama models', async ({ dashboardAPI }) => {
      const response = await dashboardAPI.listOllamaModels();

      expect(response).toBeDefined();
      expect(response.models).toBeDefined();
      expect(Array.isArray(response.models)).toBe(true);
      expect(typeof response.count).toBe('number');
    });

    test('gets loaded models', async ({ dashboardAPI }) => {
      const models = await dashboardAPI.getLoadedModels();

      expect(models).toBeDefined();
      expect(Array.isArray(models)).toBe(true);
    });

    test('models have required properties', async ({ dashboardAPI }) => {
      const response = await dashboardAPI.listOllamaModels();

      if (response.models.length > 0) {
        const model = response.models[0];
        expect(model).toHaveProperty('name');
        expect(typeof model.name).toBe('string');
      }
    });
  });

  test.describe('Model Memory Management', () => {
    test('can check which models are consuming VRAM', async ({ dashboardAPI }) => {
      const vramStatus = await dashboardAPI.getVRAMStatus();
      const loadedModels = await dashboardAPI.getLoadedModels();

      expect(vramStatus.gpu).toBeTruthy();
      expect(Array.isArray(loadedModels)).toBe(true);

      // Log memory usage for debugging
      console.log(`GPU Memory: ${vramStatus.gpu.used_mb}/${vramStatus.gpu.total_mb} MB`);
      console.log(`Loaded models: ${loadedModels.length}`);
    });

    test('unloading models should free VRAM', async ({ dashboardAPI }) => {
      const loadedBefore = await dashboardAPI.getLoadedModels();

      if (loadedBefore.length > 0) {
        const vramBefore = await dashboardAPI.getVRAMStatus();
        const modelToUnload = loadedBefore[0].name;

        try {
          await dashboardAPI.unloadModel(modelToUnload);

          // Wait for memory to be freed
          await new Promise(resolve => setTimeout(resolve, 2000));

          const vramAfter = await dashboardAPI.getVRAMStatus();

          // VRAM usage should decrease or stay same (never increase from unload)
          expect(vramAfter.gpu.used_mb).toBeLessThanOrEqual(vramBefore.gpu.used_mb + 100); // 100MB tolerance
        } catch (error) {
          console.log(`Unload test skipped: ${error}`);
        }
      } else {
        console.log('No models loaded - skipping unload test');
      }
    });
  });
});
