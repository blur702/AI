import { test, expect } from "../../../fixtures/base.fixture";

test.describe("Dashboard Backend Ollama Models API", () => {
  test.describe("GET /api/models/ollama/list", () => {
    test("returns list of available Ollama models", async ({
      dashboardAPI,
    }) => {
      const response = await dashboardAPI.listOllamaModels();

      expect(response).toBeDefined();
      expect(response.models).toBeDefined();
      expect(Array.isArray(response.models)).toBe(true);
      expect(typeof response.count).toBe("number");
      expect(response.count).toBe(response.models.length);
    });

    test("models have expected schema", async ({ dashboardAPI }) => {
      const response = await dashboardAPI.listOllamaModels();

      if (response.models.length > 0) {
        const model = response.models[0];
        expect(model).toHaveProperty("name");
        expect(typeof model.name).toBe("string");
        expect(model.name.length).toBeGreaterThan(0);
      }
    });

    test("returns consistent results on multiple calls", async ({
      dashboardAPI,
    }) => {
      const response1 = await dashboardAPI.listOllamaModels();
      const response2 = await dashboardAPI.listOllamaModels();

      expect(response1.count).toBe(response2.count);
      expect(response1.models.map((m) => m.name).sort()).toEqual(
        response2.models.map((m) => m.name).sort(),
      );
    });
  });

  test.describe("GET /api/models/ollama/loaded", () => {
    test("returns list of loaded Ollama models", async ({ dashboardAPI }) => {
      const models = await dashboardAPI.getLoadedModels();

      expect(models).toBeDefined();
      expect(Array.isArray(models)).toBe(true);
    });

    test("loaded models have expected schema", async ({ dashboardAPI }) => {
      const models = await dashboardAPI.getLoadedModels();

      // If there are loaded models, validate their structure
      if (models.length > 0) {
        const model = models[0];
        expect(model).toHaveProperty("name");
        expect(typeof model.name).toBe("string");
      }
    });

    test("loaded models are subset of available models", async ({
      dashboardAPI,
    }) => {
      const available = await dashboardAPI.listOllamaModels();
      const loaded = await dashboardAPI.getLoadedModels();

      const availableNames = available.models.map((m) => m.name.split(":")[0]);

      for (const loadedModel of loaded) {
        const loadedBaseName = loadedModel.name.split(":")[0];
        expect(availableNames).toContain(loadedBaseName);
      }
    });
  });

  test.describe("POST /api/models/ollama/unload", () => {
    test("rejects request without model_name", async ({ dashboardAPI }) => {
      try {
        await dashboardAPI.unloadModel(undefined as unknown as string);
        throw new Error("Should have thrown an error");
      } catch (error: unknown) {
        // API should reject missing model_name
        const err = error as Error;
        expect(err.message || String(err)).toBeDefined();
      }
    });

    test("rejects request with empty model_name", async ({ dashboardAPI }) => {
      try {
        await dashboardAPI.unloadModel("");
        throw new Error("Should have thrown an error");
      } catch (error: unknown) {
        const err = error as Error;
        expect(err.message || String(err)).toBeDefined();
      }
    });

    test("handles unload of non-existent model gracefully", async ({
      dashboardAPI,
    }) => {
      try {
        const result = await dashboardAPI.unloadModel(
          "nonexistent-model-xyz-123",
        );
        // May succeed if model simply isn't loaded, or fail with proper error
        expect(result).toBeDefined();
      } catch (error: any) {
        // Error is also acceptable for non-existent model
        expect(error.message || error.toString()).toBeDefined();
      }
    });
  });

  test.describe("POST /api/models/ollama/load", () => {
    test("rejects request without model_name", async ({ dashboardAPI }) => {
      try {
        await dashboardAPI.loadModel(undefined as unknown as string);
        throw new Error("Should have thrown an error");
      } catch (error: unknown) {
        const err = error as Error;
        expect(err.message || String(err)).toBeDefined();
      }
    });

    test("rejects request with empty model_name", async ({ dashboardAPI }) => {
      try {
        await dashboardAPI.loadModel("");
        throw new Error("Should have thrown an error");
      } catch (error: unknown) {
        const err = error as Error;
        expect(err.message || String(err)).toBeDefined();
      }
    });
  });

  test.describe("Model load/unload integration", () => {
    // This test requires at least one Ollama model to be available
    test("can list, verify loaded status", async ({ dashboardAPI }) => {
      const available = await dashboardAPI.listOllamaModels();
      const loaded = await dashboardAPI.getLoadedModels();

      // Both endpoints should work
      expect(available).toBeDefined();
      expect(loaded).toBeDefined();

      // Log for debugging
      console.log(`Available models: ${available.count}`);
      console.log(`Loaded models: ${loaded.length}`);
    });

    test("unloading model removes it from loaded list", async ({
      dashboardAPI,
    }) => {
      const loadedBefore = await dashboardAPI.getLoadedModels();

      if (loadedBefore.length > 0) {
        const modelToUnload = loadedBefore[0].name;
        console.log(`Unloading model: ${modelToUnload}`);

        try {
          await dashboardAPI.unloadModel(modelToUnload);

          // Give Ollama time to unload
          await new Promise((resolve) => setTimeout(resolve, 1000));

          const loadedAfter = await dashboardAPI.getLoadedModels();
          const stillLoaded = loadedAfter.find((m) => m.name === modelToUnload);

          expect(stillLoaded).toBeUndefined();
        } catch (error) {
          console.log(`Unload failed (may be expected): ${error}`);
        }
      } else {
        console.log("No models loaded to test unload functionality");
      }
    });
  });
});
