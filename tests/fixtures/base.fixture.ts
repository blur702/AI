import { test as base, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { DashboardAPIClient } from '../api-clients/DashboardAPIClient';
import { GatewayAPIClient } from '../api-clients/GatewayAPIClient';
import { ScreenshotManager } from '../utils/screenshot-manager';
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

export const test = base.extend<{
  dashboardAPI: DashboardAPIClient;
  gatewayAPI: GatewayAPIClient;
  testData: TestData;
  screenshotManager: ScreenshotManager;
  cleanupJobs: CleanupJobs;
  cleanupAPIKeys: CleanupAPIKeys;
}>({
  dashboardAPI: async ({}, use) => {
    // Single-port deployment: Dashboard serves frontend + API on port 80
    // Override with DASHBOARD_API_URL env var for remote testing (e.g., production, staging)
    const url = process.env.DASHBOARD_API_URL || 'http://localhost';
    await use(new DashboardAPIClient(url));
  },

  gatewayAPI: async ({}, use) => {
    const url = process.env.GATEWAY_API_URL || 'http://localhost:1301';
    await use(new GatewayAPIClient(url));
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
