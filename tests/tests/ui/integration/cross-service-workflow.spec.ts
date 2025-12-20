import { test, expect } from "../../../fixtures/base.fixture";

test.describe("Cross-service workflow", () => {
  // Skip: This test requires API key authentication and running backend services
  test.skip("can orchestrate a simple workflow across services", async ({
    gatewayAPI,
  }) => {
    const response = await gatewayAPI.generateImage({
      prompt: "Simple cross service test image",
    });
    expect(response.success).toBe(true);
  });
});
