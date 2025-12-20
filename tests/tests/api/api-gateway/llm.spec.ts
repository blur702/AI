import { test, expect } from "../../../fixtures/base.fixture";
import { assertAPIResponse } from "../../../utils/assertion-helpers";

test.describe("API Gateway LLM endpoints", () => {
  // Skip: This test requires API key authentication and running Ollama service
  test.skip("LLM generation works with a simple prompt", async ({
    gatewayAPI,
    testData,
  }) => {
    const prompt = testData.prompts.llm[0];
    const response = await gatewayAPI.generateLLM({ prompt: prompt.prompt });
    assertAPIResponse(response, "success");
  });

  test("models listing returns a valid response", async ({ gatewayAPI }) => {
    // Perform early connectivity check
    let isGatewayAvailable = true;
    try {
      await gatewayAPI.listModels();
    } catch (error: any) {
      if (
        error.code === "ECONNREFUSED" ||
        error.message?.includes("ECONNREFUSED")
      ) {
        isGatewayAvailable = false;
      }
    }

    // Skip test if gateway is not running
    test.skip(!isGatewayAvailable, "API Gateway is not running (port 1301)");

    // Run actual test assertions
    const response = await gatewayAPI.listModels();
    assertAPIResponse(response, "success");

    const data = response.data;
    expect(data).toBeDefined();
    expect(data.models).toBeDefined();
    expect(Array.isArray(data.models)).toBe(true);
  });
});
