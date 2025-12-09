import { test as base, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { DashboardAPIClient } from '../api-clients/DashboardAPIClient';
import { GatewayAPIClient } from '../api-clients/GatewayAPIClient';
import { ScreenshotManager } from '../utils/screenshot-manager';
import { ServiceOrchestrator } from '../utils/service-orchestrator';
import { isVPSEnvironment, getVPSConfig, ServiceId } from '../utils/vps-helpers';
import prompts from '../test-data/prompts.json';
import models from '../test-data/models.json';

export interface TestData {
  prompts: typeof prompts;
  models: typeof models;
}

export interface CleanupJobs {
  registerJob(id: string): void;
}

export interface CleanupAPIKeys {
  registerAPIKey(key: string): void;
}

export interface ServiceEnsurer {
  /**
   * Ensure a service is running before test execution.
   * In VPS mode, this will start the service if it's not running.
   * In local mode, this is a no-op (assumes services are managed externally).
   */
  ensureService(serviceId: ServiceId): Promise<void>;

  /**
   * Ensure multiple services are running.
   */
  ensureServices(serviceIds: ServiceId[]): Promise<void>;
}

export const test = base.extend<{
  dashboardAPI: DashboardAPIClient;
  gatewayAPI: GatewayAPIClient;
  testData: TestData;
  screenshotManager: ScreenshotManager;
  cleanupJobs: CleanupJobs;
  cleanupAPIKeys: CleanupAPIKeys;
  serviceOrchestrator: ServiceOrchestrator | null;
  ensureServices: ServiceEnsurer;
}>({
  dashboardAPI: async ({}, use) => {
    // Single-port deployment: Dashboard serves frontend + API on port 80
    // Override with DASHBOARD_API_URL env var for remote testing (e.g., production, staging)
    const url = process.env.DASHBOARD_API_URL || 'http://localhost';
    // Allow insecure connections for self-signed certs in test environments
    const allowInsecure = process.env.ALLOW_INSECURE_CONNECTIONS === 'true';
    await use(new DashboardAPIClient(url, { allowInsecureConnections: allowInsecure }));
  },

  gatewayAPI: async ({}, use) => {
    const url = process.env.GATEWAY_API_URL || 'http://localhost:1301';
    // Allow insecure connections for self-signed certs in test environments
    const allowInsecure = process.env.ALLOW_INSECURE_CONNECTIONS === 'true';
    await use(new GatewayAPIClient(url, { allowInsecureConnections: allowInsecure }));
  },

  testData: async ({}, use) => {
    await use({ prompts, models });
  },

  screenshotManager: async ({ page }, use) => {
    const baseDir = path.resolve(process.cwd(), 'tests', 'screenshots');
    if (!fs.existsSync(baseDir)) {
      fs.mkdirSync(baseDir, { recursive: true });
    }
    const manager = new ScreenshotManager(baseDir);
    await use(manager);
  },

  serviceOrchestrator: async ({ dashboardAPI }, use) => {
    // Only create orchestrator in VPS mode
    if (!isVPSEnvironment()) {
      await use(null);
      return;
    }

    const vpsConfig = getVPSConfig();
    const orchestrator = new ServiceOrchestrator(dashboardAPI, {
      startTimeout: vpsConfig.serviceStartTimeout,
      healthInterval: vpsConfig.serviceHealthInterval,
      maxRetries: vpsConfig.maxServiceRetries,
      preserveEmbeddingModels: vpsConfig.preserveEmbeddingModels,
      gpuIntensiveServices: vpsConfig.gpuIntensiveServices
    });

    await use(orchestrator);

    // Cleanup: orchestrator handles its own cleanup
  },

  ensureServices: async ({ serviceOrchestrator }, use) => {
    const ensurer: ServiceEnsurer = {
      async ensureService(serviceId: ServiceId): Promise<void> {
        if (!serviceOrchestrator) {
          // Local mode: assume services are managed externally
          return;
        }
        await serviceOrchestrator.ensureServiceRunning(serviceId);
      },

      async ensureServices(serviceIds: ServiceId[]): Promise<void> {
        if (!serviceOrchestrator) {
          // Local mode: assume services are managed externally
          return;
        }
        await serviceOrchestrator.startServicesForSuite(serviceIds);
      }
    };

    await use(ensurer);
  },

  cleanupJobs: async ({ gatewayAPI }, use) => {
    const jobIds: string[] = [];
    await use({
      registerJob(id: string) {
        jobIds.push(id);
      }
    });

    for (const id of jobIds) {
      try {
        await gatewayAPI.cancelJob(id);
      } catch (error) {
        console.warn(`Failed to cleanup job ${id}`, error);
      }
    }
  },

  cleanupAPIKeys: async ({ gatewayAPI }, use) => {
    const apiKeys: string[] = [];
    await use({
      registerAPIKey(key: string) {
        apiKeys.push(key);
      }
    });

    // Cleanup: deactivate all registered API keys
    for (const key of apiKeys) {
      try {
        await gatewayAPI.deactivateAPIKey(key);
      } catch (error) {
        console.warn(`Failed to cleanup API key ${key}`, error);
      }
    }
  }
});

export { expect };
