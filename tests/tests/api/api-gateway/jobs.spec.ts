import { test, expect } from "../../../fixtures/base.fixture";

test.describe("API Gateway job management", () => {
  test("job listing works", async ({ gatewayAPI }) => {
    try {
      const response = await gatewayAPI.listJobs(0, 5);
      expect(response.success).toBe(true);
    } catch (error: any) {
      // Skip test if gateway is not running (ECONNREFUSED)
      if (
        error.code === "ECONNREFUSED" ||
        error.message?.includes("ECONNREFUSED")
      ) {
        test.skip(true, "API Gateway is not running (port 1301)");
        return;
      }
      throw error;
    }
  });
});
