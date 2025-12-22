import { test, expect } from "../../../fixtures/base.fixture";
import { assertAPIResponse } from "../../../utils/assertion-helpers";
import { APIError } from "../../../api-clients/BaseAPIClient";

/**
 * Helper to check if the gateway is available and skip tests if not.
 */
async function checkGatewayAvailable(gatewayAPI: any): Promise<boolean> {
  try {
    await gatewayAPI.getHealth();
    return true;
  } catch (error: any) {
    if (
      error.code === "ECONNREFUSED" ||
      error.message?.includes("ECONNREFUSED")
    ) {
      return false;
    }
    throw error;
  }
}

test.describe("API Gateway Authentication", () => {
  test.describe("API Key Creation", () => {
    test("creates API key with valid name", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      const response = await gatewayAPI.createAPIKey("test-key-1");

      expect(response.success).toBe(true);
      expect(response.data).toBeDefined();
      expect(response.data.key).toBeDefined();
      expect(response.data.key.length).toBeGreaterThanOrEqual(32);
      expect(response.data.name).toBe("test-key-1");
      expect(response.data.created_at).toBeDefined();

      // Validate created_at is a valid ISO timestamp
      const createdAt = new Date(response.data.created_at);
      expect(createdAt.getTime()).not.toBeNaN();

      // Register for cleanup
      cleanupAPIKeys.registerAPIKey(response.data.key);
    });

    test("creates multiple API keys with different names", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      const keys: string[] = [];
      const names = ["multi-key-1", "multi-key-2", "multi-key-3"];

      for (const name of names) {
        const response = await gatewayAPI.createAPIKey(name);
        expect(response.success).toBe(true);
        expect(response.data.key).toBeDefined();
        keys.push(response.data.key);
        cleanupAPIKeys.registerAPIKey(response.data.key);
      }

      // Verify all keys are unique
      const uniqueKeys = new Set(keys);
      expect(uniqueKeys.size).toBe(keys.length);
    });
  });

  test.describe("API Key Listing", () => {
    test("lists all API keys without exposing key values", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create 2 test keys
      const key1Response = await gatewayAPI.createAPIKey("list-test-key-1");
      const key2Response = await gatewayAPI.createAPIKey("list-test-key-2");
      cleanupAPIKeys.registerAPIKey(key1Response.data.key);
      cleanupAPIKeys.registerAPIKey(key2Response.data.key);

      // List all keys
      const listResponse = await gatewayAPI.listAPIKeys();

      expect(listResponse.success).toBe(true);
      expect(listResponse.data).toBeDefined();
      expect(listResponse.data.keys).toBeDefined();
      expect(Array.isArray(listResponse.data.keys)).toBe(true);
      expect(listResponse.data.keys.length).toBeGreaterThanOrEqual(2);

      // Check each key has required fields but NOT the actual key value
      for (const keyInfo of listResponse.data.keys) {
        expect(keyInfo.name).toBeDefined();
        expect(keyInfo.created_at).toBeDefined();
        expect(keyInfo).toHaveProperty("last_used_at");
        expect(keyInfo).toHaveProperty("is_active");
        // The actual key value should NOT be exposed in the list
        expect((keyInfo as any).key).toBeUndefined();
      }
    });

    test("shows correct is_active status", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create a key
      const createResponse =
        await gatewayAPI.createAPIKey("active-status-test");
      const apiKey = createResponse.data.key;
      cleanupAPIKeys.registerAPIKey(apiKey);

      // Verify it's active in the list
      let listResponse = await gatewayAPI.listAPIKeys();
      let keyInfo = listResponse.data.keys.find(
        (k: any) => k.name === "active-status-test",
      );
      expect(keyInfo).toBeDefined();
      expect(keyInfo.is_active).toBe(true);

      // Deactivate the key
      await gatewayAPI.deactivateAPIKey(apiKey);

      // Verify it's now inactive
      listResponse = await gatewayAPI.listAPIKeys();
      keyInfo = listResponse.data.keys.find(
        (k: any) => k.name === "active-status-test",
      );
      expect(keyInfo).toBeDefined();
      expect(keyInfo.is_active).toBe(false);
    });
  });

  test.describe("API Key Deactivation", () => {
    test("deactivates existing API key", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create a key
      const createResponse = await gatewayAPI.createAPIKey("deactivate-test");
      const apiKey = createResponse.data.key;
      cleanupAPIKeys.registerAPIKey(apiKey);

      // Deactivate it
      const deactivateResponse = await gatewayAPI.deactivateAPIKey(apiKey);
      expect(deactivateResponse.success).toBe(true);

      // Verify it's inactive in the list
      const listResponse = await gatewayAPI.listAPIKeys();
      const keyInfo = listResponse.data.keys.find(
        (k: any) => k.name === "deactivate-test",
      );
      expect(keyInfo).toBeDefined();
      expect(keyInfo.is_active).toBe(false);
    });

    test("deactivation is idempotent", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create a key
      const createResponse = await gatewayAPI.createAPIKey("idempotent-test");
      const apiKey = createResponse.data.key;
      cleanupAPIKeys.registerAPIKey(apiKey);

      // Deactivate twice
      const firstDeactivate = await gatewayAPI.deactivateAPIKey(apiKey);
      expect(firstDeactivate.success).toBe(true);

      const secondDeactivate = await gatewayAPI.deactivateAPIKey(apiKey);
      expect(secondDeactivate.success).toBe(true);
    });

    test("deactivating non-existent key succeeds", async ({ gatewayAPI }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Try to deactivate a non-existent key
      const response = await gatewayAPI.deactivateAPIKey(
        "non-existent-key-12345",
      );
      expect(response.success).toBe(true);
    });
  });

  test.describe("Middleware - Valid API Key", () => {
    test("allows access to protected endpoint with valid API key", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create a valid API key
      const createResponse = await gatewayAPI.createAPIKey(
        "protected-endpoint-test",
      );
      const apiKey = createResponse.data.key;
      cleanupAPIKeys.registerAPIKey(apiKey);

      // Create authenticated client
      const authenticatedClient = gatewayAPI.withAPIKey(apiKey);

      // Try to access a protected endpoint (POST /llm/generate)
      // Note: This may fail with other errors if Ollama is not running,
      // but it should NOT be a 401 Unauthorized error
      try {
        await authenticatedClient.generateLLM({ prompt: "Hello" });
        // If it succeeds, great
      } catch (error: any) {
        // If it fails, verify it's NOT a 401 error
        if (error instanceof APIError) {
          expect(error.status).not.toBe(401);
        }
      }
    });

    test("updates last_used_at timestamp on API key usage", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create a key
      const createResponse = await gatewayAPI.createAPIKey("timestamp-test");
      const apiKey = createResponse.data.key;
      cleanupAPIKeys.registerAPIKey(apiKey);

      // Check initial last_used_at (should be null)
      let listResponse = await gatewayAPI.listAPIKeys();
      let keyInfo = listResponse.data.keys.find(
        (k: any) => k.name === "timestamp-test",
      );
      expect(keyInfo).toBeDefined();
      const initialLastUsed = keyInfo.last_used_at;

      // Make an authenticated request to a PROTECTED endpoint (POST /llm/generate)
      // This exercises the API key middleware which updates last_used_at.
      // Note: The request may fail due to missing Ollama service, but as long as
      // authentication succeeds (no 401), the middleware will have updated last_used_at.
      const authenticatedClient = gatewayAPI.withAPIKey(apiKey);
      try {
        await authenticatedClient.generateLLM({ prompt: "test" });
      } catch (error: any) {
        // Only fail if we get a 401 - that means the API key wasn't accepted
        if (error instanceof APIError && error.status === 401) {
          throw new Error(
            "API key should have been accepted but got 401 Unauthorized",
          );
        }
        // Other errors (e.g., Ollama not running) are expected and ignored
      }

      // Wait a moment for the update to propagate
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Check last_used_at is now set
      listResponse = await gatewayAPI.listAPIKeys();
      keyInfo = listResponse.data.keys.find(
        (k: any) => k.name === "timestamp-test",
      );
      expect(keyInfo).toBeDefined();

      // last_used_at should be updated (either from null to a value, or to a newer value)
      if (initialLastUsed === null) {
        expect(keyInfo.last_used_at).not.toBeNull();
      } else {
        const initial = new Date(initialLastUsed).getTime();
        const updated = new Date(keyInfo.last_used_at).getTime();
        expect(updated).toBeGreaterThanOrEqual(initial);
      }
    });
  });

  test.describe("Middleware - Invalid API Key", () => {
    test("rejects request with missing API key header", async ({
      gatewayAPI,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Try to access protected endpoint without API key
      let didThrow = false;
      try {
        await gatewayAPI.generateLLM({ prompt: "Hello" });
      } catch (error: any) {
        didThrow = true;
        expect(error).toBeInstanceOf(APIError);
        expect(error.status).toBe(401);
        expect(error.data?.success).toBe(false);
        expect(error.data?.error?.code).toBe("INVALID_API_KEY");
        expect(error.data?.error?.message).toContain("Missing API key");
      }
      expect(didThrow).toBe(true);
    });

    test("rejects request with invalid API key", async ({ gatewayAPI }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create client with invalid key
      const invalidClient = gatewayAPI.withAPIKey("invalid-key-12345");

      let didThrow = false;
      try {
        await invalidClient.generateLLM({ prompt: "Hello" });
      } catch (error: any) {
        didThrow = true;
        expect(error).toBeInstanceOf(APIError);
        expect(error.status).toBe(401);
        expect(error.data?.success).toBe(false);
        expect(error.data?.error?.code).toBe("INVALID_API_KEY");
      }
      expect(didThrow).toBe(true);
    });

    test("rejects request with deactivated API key", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Create and deactivate a key
      const createResponse = await gatewayAPI.createAPIKey(
        "deactivated-key-test",
      );
      const apiKey = createResponse.data.key;
      cleanupAPIKeys.registerAPIKey(apiKey);

      await gatewayAPI.deactivateAPIKey(apiKey);

      // Try to use deactivated key
      const deactivatedClient = gatewayAPI.withAPIKey(apiKey);

      let didThrow = false;
      try {
        await deactivatedClient.generateLLM({ prompt: "Hello" });
      } catch (error: any) {
        didThrow = true;
        expect(error).toBeInstanceOf(APIError);
        expect(error.status).toBe(401);
        expect(error.data?.success).toBe(false);
        expect(error.data?.error?.code).toBe("INVALID_API_KEY");
        expect(error.data?.error?.message).toContain(
          "Invalid or inactive API key",
        );
      }
      expect(didThrow).toBe(true);
    });
  });

  test.describe("Public Endpoint Access", () => {
    test("allows access to /health without API key", async ({ gatewayAPI }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      const response = await gatewayAPI.getHealth();
      expect(response.success).toBe(true);
    });

    test("allows GET /jobs without API key", async ({ gatewayAPI }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      const response = await gatewayAPI.listJobs();
      expect(response.success).toBe(true);
    });

    test("allows GET /llm/models without API key", async ({ gatewayAPI }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      const response = await gatewayAPI.listModels();
      assertAPIResponse(response, "success");
    });

    test("requires API key for POST /llm/generate", async ({ gatewayAPI }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      let didThrow = false;
      try {
        await gatewayAPI.generateLLM({ prompt: "Hello" });
      } catch (error: any) {
        didThrow = true;
        expect(error).toBeInstanceOf(APIError);
        expect(error.status).toBe(401);
      }
      expect(didThrow).toBe(true);
    });
  });

  test.describe("Error Handling", () => {
    test("handles gateway unavailable gracefully", async ({ gatewayAPI }) => {
      // This test is expected to skip if gateway is not running
      // But if we reach here, we verify error handling works
      try {
        await gatewayAPI.getHealth();
        // Gateway is available, test passes
      } catch (error: any) {
        if (
          error.code === "ECONNREFUSED" ||
          error.message?.includes("ECONNREFUSED")
        ) {
          test.skip(
            true,
            "API Gateway is not running - this is expected behavior",
          );
          return;
        }
        // Other errors should be thrown
        throw error;
      }
    });

    test("validates response format for all endpoints", async ({
      gatewayAPI,
      cleanupAPIKeys,
    }) => {
      const isAvailable = await checkGatewayAvailable(gatewayAPI);
      test.skip(!isAvailable, "API Gateway is not running (port 1301)");

      // Test health endpoint response format
      const healthResponse = await gatewayAPI.getHealth();
      expect(healthResponse).toHaveProperty("success");
      expect(typeof healthResponse.success).toBe("boolean");

      // Test create API key response format
      const createResponse = await gatewayAPI.createAPIKey("format-test");
      expect(createResponse).toHaveProperty("success");
      expect(createResponse).toHaveProperty("data");
      cleanupAPIKeys.registerAPIKey(createResponse.data.key);

      // Test list API keys response format
      const listResponse = await gatewayAPI.listAPIKeys();
      expect(listResponse).toHaveProperty("success");
      expect(listResponse).toHaveProperty("data");
      expect(listResponse.data).toHaveProperty("keys");

      // Test deactivate response format
      const deactivateResponse = await gatewayAPI.deactivateAPIKey(
        createResponse.data.key,
      );
      expect(deactivateResponse).toHaveProperty("success");
    });
  });
});
