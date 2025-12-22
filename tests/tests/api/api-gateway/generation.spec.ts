import { test, expect } from "../../../fixtures/base.fixture";

test.describe("API Gateway generation endpoints", () => {
  // Skip: These tests require API key authentication and running backend services
  test.skip("image generation returns a job or result", async ({
    gatewayAPI,
    testData,
  }) => {
    const prompt = testData.prompts.image[0];
    const response = await gatewayAPI.generateImage({ prompt: prompt.prompt });
    expect(response.success).toBe(true);
  });

  test.skip("music generation returns a job or result", async ({
    gatewayAPI,
    testData,
  }) => {
    const prompt = testData.prompts.music[0];
    const response = await gatewayAPI.generateMusic({ prompt: prompt.prompt });
    expect(response.success).toBe(true);
  });
});
