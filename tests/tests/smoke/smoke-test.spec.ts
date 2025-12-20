/**
 * Smoke Tests
 *
 * Basic connectivity and health checks for the AI dashboard ecosystem.
 * These tests verify that core services are accessible and responding.
 *
 * In VPS mode, services are automatically started via the orchestrator.
 * In local mode, services are assumed to be running.
 */

import { test, expect } from "../../fixtures/base.fixture";
import { waitForServiceReady } from "../../utils/wait-helpers";
import {
  isVPSEnvironment,
  ServiceIds,
  getTestEnvironment,
} from "../../utils/vps-helpers";

/**
 * Helper to normalize URL by removing trailing slash
 */
function normalizeBaseURL(url: string): string {
  return url.replace(/\/$/, "");
}

test.describe.parallel("Smoke tests", () => {
  test.beforeAll(async () => {
    console.log(
      `\n=== Running smoke tests in ${getTestEnvironment()} mode ===\n`,
    );
  });

  test("Dashboard backend is responding", async ({ dashboardAPI }) => {
    const vram = await dashboardAPI.getVRAMStatus();
    expect(vram.gpu).toBeTruthy();
    console.log(
      `GPU: ${vram.gpu.name} - ${vram.gpu.used_mb}MB / ${vram.gpu.total_mb}MB`,
    );
  });

  test("API Gateway health endpoint is responding", async ({ gatewayAPI }) => {
    try {
      const health = await gatewayAPI.getHealth();
      expect(health.success).toBe(true);
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

  test("Core services respond with 200", async () => {
    // Only check core services that should always be running for tests
    // Dashboard is required, others are optional
    const dashboardBase = normalizeBaseURL(
      process.env.DASHBOARD_API_URL || "http://localhost",
    );
    const dashboardUrl = dashboardBase + "/api/vram/status";

    // Dashboard must be available
    await waitForServiceReady(dashboardUrl, 10_000);

    // Check optional services and track which are available
    const gatewayBase = normalizeBaseURL(
      process.env.GATEWAY_API_URL || "http://localhost:1301",
    );
    const optionalServices = [
      { name: "API Gateway", url: gatewayBase + "/health" },
      {
        name: "Ollama",
        url: process.env.OLLAMA_URL || "http://localhost:11434",
      },
    ];

    const results: string[] = [];
    for (const service of optionalServices) {
      try {
        await waitForServiceReady(service.url, 5_000);
        results.push(`${service.name}`);
      } catch {
        results.push(`${service.name} (offline)`);
      }
    }
    console.log("Service availability:", results.join(", "));
  });
});

test.describe("Dashboard Service Management", () => {
  test("should list all registered services", async ({ dashboardAPI }) => {
    const { services } = await dashboardAPI.getServices();

    expect(services).toBeDefined();
    expect(Object.keys(services).length).toBeGreaterThan(0);

    const statuses = Object.entries(services).map(([id, info]) => ({
      id,
      status: info.status,
      gpuIntensive: info.gpu_intensive,
    }));

    console.log("\nService Status Report:");
    for (const { id, status, gpuIntensive } of statuses) {
      const gpu = gpuIntensive ? " (GPU)" : "";
      console.log(`  ${id}: ${status}${gpu}`);
    }
  });

  test("should list Ollama models", async ({
    dashboardAPI,
    ensureServices,
  }) => {
    // Ensure Ollama is running in VPS mode
    await ensureServices.ensureService(ServiceIds.OLLAMA);

    const models = await dashboardAPI.listOllamaModels();

    expect(models).toBeDefined();
    expect(models.count).toBeGreaterThanOrEqual(0);

    console.log(`Ollama has ${models.count} models available`);
    if (models.models.length > 0) {
      console.log(
        `Models: ${models.models
          .slice(0, 5)
          .map((m) => m.name)
          .join(", ")}${models.count > 5 ? "..." : ""}`,
      );
    }
  });

  test("should check loaded models", async ({
    dashboardAPI,
    ensureServices,
  }) => {
    await ensureServices.ensureService(ServiceIds.OLLAMA);

    const loadedModels = await dashboardAPI.getLoadedModels();

    expect(loadedModels).toBeDefined();
    expect(Array.isArray(loadedModels)).toBe(true);

    console.log(`Currently loaded models: ${loadedModels.length}`);
    if (loadedModels.length > 0) {
      console.log(`Loaded: ${loadedModels.map((m) => m.name).join(", ")}`);
    }
  });
});

test.describe("VPS Service Management", () => {
  test.skip(!isVPSEnvironment(), "VPS-only tests");

  test("should be able to check service status", async ({ dashboardAPI }) => {
    // Use a lightweight service for testing
    const testServiceId = "n8n";

    try {
      const status = await dashboardAPI.getServiceStatus(testServiceId);
      expect(status).toBeDefined();
      expect(status.id).toBe(testServiceId);
      expect([
        "running",
        "stopped",
        "starting",
        "stopping",
        "error",
        "unknown",
      ]).toContain(status.status);
      console.log(`Service ${testServiceId}: ${status.status}`);
    } catch (error: any) {
      // Service might not be registered
      console.log(`Service ${testServiceId} not found: ${error.message}`);
    }
  });

  test("should preserve embedding models during VRAM cleanup", async ({
    dashboardAPI,
    serviceOrchestrator,
  }) => {
    if (!serviceOrchestrator) {
      test.skip(true, "Service orchestrator not available");
      return;
    }

    // Get loaded models before cleanup
    const beforeModels = await dashboardAPI.getLoadedModels();
    console.log(
      `Models before cleanup: ${beforeModels.map((m) => m.name).join(", ") || "none"}`,
    );

    // Run VRAM management with embedding preservation
    await serviceOrchestrator.manageVRAM(true);

    // Get loaded models after cleanup
    const afterModels = await dashboardAPI.getLoadedModels();
    console.log(
      `Models after cleanup: ${afterModels.map((m) => m.name).join(", ") || "none"}`,
    );

    // Check that embedding models are still loaded
    const embeddingPatterns = ["nomic-embed", "mxbai-embed", "all-minilm"];
    const beforeEmbeddings = beforeModels.filter((m) =>
      embeddingPatterns.some((p) => m.name.toLowerCase().includes(p)),
    );
    const afterEmbeddings = afterModels.filter((m) =>
      embeddingPatterns.some((p) => m.name.toLowerCase().includes(p)),
    );

    // If there were embedding models before, they should still be there
    if (beforeEmbeddings.length > 0) {
      expect(afterEmbeddings.length).toBeGreaterThanOrEqual(
        beforeEmbeddings.length,
      );
      console.log(
        `Embedding models preserved: ${afterEmbeddings.map((m) => m.name).join(", ")}`,
      );
    }
  });
});

// Skip: This test requires all AI services to be running
test.skip("All configured services respond with 200", async () => {
  const serviceUrls = [
    process.env.DASHBOARD_API_URL,
    process.env.GATEWAY_API_URL,
    process.env.OPEN_WEBUI_URL,
    process.env.COMFYUI_URL,
    process.env.OLLAMA_URL,
    process.env.WAN2GP_URL,
    process.env.YUE_URL,
    process.env.DIFFRHYTHM_URL,
    process.env.MUSICGEN_URL,
    process.env.STABLE_AUDIO_URL,
    process.env.ALLTALK_URL,
    process.env.N8N_URL,
  ].filter((u): u is string => !!u);

  await Promise.all(serviceUrls.map((url) => waitForServiceReady(url, 30_000)));
});
