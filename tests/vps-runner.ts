/**
 * VPS Test Runner
 *
 * CLI utility for orchestrating test execution on VPS with automatic service management.
 * This file is a standalone CLI helper, NOT a Playwright global setup.
 *
 * For Playwright global setup, see vps-setup.ts which is the single entrypoint
 * referenced by playwright.config.ts and vps.config.ts.
 *
 * Usage:
 *   npx ts-node tests/vps-runner.ts [suite]
 *   npx ts-node tests/vps-runner.ts smoke --cleanup
 *
 * Suites: smoke, api, ui, image, audio, music, video, llm
 */

import { DashboardAPIClient } from "./api-clients/DashboardAPIClient";
import { GatewayAPIClient } from "./api-clients/GatewayAPIClient";
import { ServiceOrchestrator } from "./utils/service-orchestrator";
import {
  getVPSConfig,
  getServicesForSuite,
  logVPSEnvironment,
  isVPSEnvironment,
  ServiceIds,
} from "./utils/vps-helpers";

export interface VPSTestRunnerConfig {
  suite?: string;
  preserveEmbedding?: boolean;
  cleanupOnExit?: boolean;
}

export class VPSTestRunner {
  private dashboardClient: DashboardAPIClient;
  private gatewayClient: GatewayAPIClient;
  private orchestrator: ServiceOrchestrator;
  private config: VPSTestRunnerConfig;

  constructor(config: VPSTestRunnerConfig = {}) {
    const vpsConfig = getVPSConfig();

    this.dashboardClient = new DashboardAPIClient(vpsConfig.dashboardApiUrl, {
      allowInsecureConnections: vpsConfig.allowInsecureConnections,
    });
    this.gatewayClient = new GatewayAPIClient(vpsConfig.gatewayApiUrl, {
      allowInsecureConnections: vpsConfig.allowInsecureConnections,
    });
    this.orchestrator = new ServiceOrchestrator(this.dashboardClient, {
      startTimeout: vpsConfig.serviceStartTimeout,
      healthInterval: vpsConfig.serviceHealthInterval,
      maxRetries: vpsConfig.maxServiceRetries,
      preserveEmbeddingModels: vpsConfig.preserveEmbeddingModels,
      gpuIntensiveServices: vpsConfig.gpuIntensiveServices,
    });

    this.config = {
      suite: config.suite || "smoke",
      preserveEmbedding: config.preserveEmbedding ?? true,
      cleanupOnExit: config.cleanupOnExit ?? false,
    };
  }

  /**
   * Run smoke tests to verify basic connectivity
   */
  async runSmokeChecks(): Promise<boolean> {
    console.log("\n[VPSTestRunner] Running smoke checks...");

    try {
      // Check dashboard
      console.log("[VPSTestRunner] Checking dashboard...");
      const services = await this.dashboardClient.getServices();
      console.log(
        `[VPSTestRunner] Dashboard OK - ${Object.keys(services.services).length} services registered`,
      );

      // Check gateway
      console.log("[VPSTestRunner] Checking API gateway...");
      const health = await this.gatewayClient.healthCheck();
      console.log(
        `[VPSTestRunner] Gateway OK - Status: ${health.success ? "healthy" : "unhealthy"}`,
      );

      // Check Ollama (embedding host)
      console.log("[VPSTestRunner] Checking Ollama...");
      const models = await this.dashboardClient.listOllamaModels();
      console.log(
        `[VPSTestRunner] Ollama OK - ${models.count} models available`,
      );

      console.log("[VPSTestRunner] Smoke checks passed\n");
      return true;
    } catch (error: any) {
      console.error(`[VPSTestRunner] Smoke check failed: ${error.message}`);
      return false;
    }
  }

  /**
   * Setup: Start required services and prepare environment
   */
  async setup(): Promise<void> {
    logVPSEnvironment();

    console.log(`[VPSTestRunner] Setting up for suite: ${this.config.suite}`);

    // Run smoke checks first
    const smokeOk = await this.runSmokeChecks();
    if (!smokeOk) {
      throw new Error(
        "Smoke checks failed - dashboard or gateway not accessible",
      );
    }

    // Get required services for the suite
    const requiredServices = getServicesForSuite(this.config.suite!);
    console.log(
      `[VPSTestRunner] Required services: ${requiredServices.join(", ")}`,
    );

    // Manage VRAM before starting services
    console.log("[VPSTestRunner] Managing VRAM...");
    await this.orchestrator.manageVRAM(this.config.preserveEmbedding);

    // Start required services
    console.log("[VPSTestRunner] Starting required services...");
    await this.orchestrator.startServicesForSuite(requiredServices);

    console.log("[VPSTestRunner] Setup complete\n");
  }

  /**
   * Teardown: Stop services and cleanup
   */
  async teardown(): Promise<void> {
    console.log("[VPSTestRunner] Running teardown...");

    if (this.config.cleanupOnExit) {
      // Stop GPU-intensive services (preserve embedding hosts)
      await this.orchestrator.stopUnusedServices([
        ServiceIds.OLLAMA,
        ServiceIds.WEAVIATE,
        ServiceIds.DASHBOARD,
        ServiceIds.GATEWAY,
      ]);
    }

    console.log("[VPSTestRunner] Teardown complete\n");
  }

  /**
   * Get the orchestrator for use in tests
   */
  getOrchestrator(): ServiceOrchestrator {
    return this.orchestrator;
  }

  /**
   * Get the dashboard client
   */
  getDashboardClient(): DashboardAPIClient {
    return this.dashboardClient;
  }

  /**
   * Get the gateway client
   */
  getGatewayClient(): GatewayAPIClient {
    return this.gatewayClient;
  }
}

// CLI entrypoint
if (require.main === module) {
  const suite = process.argv[2] || "smoke";

  console.log("=== VPS Test Runner ===\n");

  const runner = new VPSTestRunner({
    suite,
    preserveEmbedding: true,
    cleanupOnExit: process.argv.includes("--cleanup"),
  });

  runner
    .setup()
    .then(() => {
      console.log("Setup successful! Ready to run tests.");
      process.exit(0);
    })
    .catch((error) => {
      console.error("Setup failed:", error.message);
      process.exit(1);
    });
}
