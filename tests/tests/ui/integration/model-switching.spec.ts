import { test, expect } from "../../../fixtures/base.fixture";

test.describe("Model switching", () => {
  test("lists available Ollama models", async ({ dashboardAPI }) => {
    const response = await dashboardAPI.listOllamaModels();
    expect(response).toBeDefined();
    expect(response.models).toBeDefined();
    expect(Array.isArray(response.models)).toBe(true);
  });

  // Skip: Loading models takes significant time and requires VRAM
  test.skip("can load and unload a model", async ({
    dashboardAPI,
    testData,
  }) => {
    const target = testData.models.ollamaModels[0];
    await dashboardAPI.loadModel(target.name);

    const loaded = await dashboardAPI.getLoadedModels();
    expect(loaded.some((m) => m.name === target.name)).toBe(true);

    await dashboardAPI.unloadModel(target.name);
  });
});
