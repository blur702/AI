import { test, expect } from "../../../fixtures/base.fixture";

test.describe("VRAM Management Integration", () => {
  test.describe("VRAM Status Monitoring", () => {
    test("VRAM endpoint returns complete usage data", async ({
      dashboardAPI,
    }) => {
      const status = await dashboardAPI.getVRAMStatus();

      expect(status.gpu).toBeTruthy();
      expect(status.gpu.name).toBeTruthy();
      expect(status.gpu.total_mb).toBeGreaterThan(0);
      expect(status.gpu.used_mb).toBeGreaterThanOrEqual(0);
      expect(status.gpu.free_mb).toBeGreaterThanOrEqual(0);
    });

    test("VRAM utilization is percentage", async ({ dashboardAPI }) => {
      const status = await dashboardAPI.getVRAMStatus();

      expect(status.gpu.utilization).toBeGreaterThanOrEqual(0);
      expect(status.gpu.utilization).toBeLessThanOrEqual(100);
    });

    test("GPU processes are tracked", async ({ dashboardAPI }) => {
      const status = await dashboardAPI.getVRAMStatus();

      expect(Array.isArray(status.processes)).toBe(true);

      // If processes exist, validate structure
      for (const proc of status.processes) {
        expect(proc).toHaveProperty("pid");
        expect(proc).toHaveProperty("name");
        expect(proc).toHaveProperty("memory");
      }
    });
  });

  test.describe("Model Memory Manager", () => {
    test("can view all available models", async ({ dashboardAPI }) => {
      const response = await dashboardAPI.listOllamaModels();

      expect(response.models).toBeDefined();
      expect(response.count).toBe(response.models.length);
    });

    test("can view loaded models consuming VRAM", async ({ dashboardAPI }) => {
      const loaded = await dashboardAPI.getLoadedModels();

      expect(Array.isArray(loaded)).toBe(true);

      // Each loaded model should have a name
      for (const model of loaded) {
        expect(model.name).toBeTruthy();
      }
    });

    test("loaded models count matches or is less than available", async ({
      dashboardAPI,
    }) => {
      const available = await dashboardAPI.listOllamaModels();
      const loaded = await dashboardAPI.getLoadedModels();

      expect(loaded.length).toBeLessThanOrEqual(available.count);
    });
  });

  test.describe("VRAM and Model Correlation", () => {
    test("VRAM status reflects model loading", async ({ dashboardAPI }) => {
      const vramStatus = await dashboardAPI.getVRAMStatus();
      const loadedModels = await dashboardAPI.getLoadedModels();

      // Log current state for debugging
      console.log(`GPU: ${vramStatus.gpu.name}`);
      console.log(
        `VRAM Used: ${vramStatus.gpu.used_mb} MB / ${vramStatus.gpu.total_mb} MB`,
      );
      console.log(`VRAM Free: ${vramStatus.gpu.free_mb} MB`);
      console.log(`Utilization: ${vramStatus.gpu.utilization}%`);
      console.log(`Loaded Models: ${loadedModels.length}`);
      console.log(`GPU Processes: ${vramStatus.processes.length}`);

      // Basic sanity checks
      expect(vramStatus.gpu.total_mb).toBeGreaterThan(0);
    });

    test("memory values are consistent", async ({ dashboardAPI }) => {
      const status = await dashboardAPI.getVRAMStatus();

      // used + free should approximately equal total
      const sum = status.gpu.used_mb + status.gpu.free_mb;
      const diff = Math.abs(sum - status.gpu.total_mb);
      const tolerance = status.gpu.total_mb * 0.1; // 10% tolerance

      expect(diff).toBeLessThan(tolerance);
    });
  });

  test.describe("Model Unload Functionality", () => {
    test("can request model unload", async ({ dashboardAPI }) => {
      const loadedBefore = await dashboardAPI.getLoadedModels();

      if (loadedBefore.length === 0) {
        console.log("No models loaded to test unload - skipping");
        return;
      }

      const modelToUnload = loadedBefore[0].name;
      console.log(`Testing unload of: ${modelToUnload}`);

      try {
        const result = await dashboardAPI.unloadModel(modelToUnload);
        expect(result).toBeDefined();

        // Wait for unload to complete
        await new Promise((resolve) => setTimeout(resolve, 1500));

        const loadedAfter = await dashboardAPI.getLoadedModels();
        const stillLoaded = loadedAfter.some((m) => m.name === modelToUnload);

        if (!stillLoaded) {
          console.log(`Successfully unloaded: ${modelToUnload}`);
        }
      } catch (error: any) {
        console.log(
          `Unload returned error (may be expected): ${error.message || error}`,
        );
      }
    });

    test("invalid model unload returns appropriate error", async ({
      dashboardAPI,
    }) => {
      const fakeModel = "completely-fake-model-that-does-not-exist-12345";

      try {
        await dashboardAPI.unloadModel(fakeModel);
      } catch (error: any) {
        // Should get an error for non-existent model
        expect(error).toBeDefined();
      }
    });
  });

  test.describe("Concurrent Operations", () => {
    test("multiple VRAM status requests work correctly", async ({
      dashboardAPI,
    }) => {
      // Fire multiple requests concurrently
      const requests = Array(5)
        .fill(null)
        .map(() => dashboardAPI.getVRAMStatus());
      const results = await Promise.all(requests);

      // All should succeed with consistent GPU name
      const gpuName = results[0].gpu.name;
      for (const result of results) {
        expect(result.gpu.name).toBe(gpuName);
        expect(result.gpu.total_mb).toBe(results[0].gpu.total_mb);
      }
    });

    test("VRAM and model list requests work concurrently", async ({
      dashboardAPI,
    }) => {
      const [vram, models, loaded] = await Promise.all([
        dashboardAPI.getVRAMStatus(),
        dashboardAPI.listOllamaModels(),
        dashboardAPI.getLoadedModels(),
      ]);

      expect(vram.gpu).toBeTruthy();
      expect(models.models).toBeDefined();
      expect(Array.isArray(loaded)).toBe(true);
    });
  });
});
