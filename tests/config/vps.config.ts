/**
 * VPS-specific Playwright configuration
 *
 * Extends the base config with VPS-optimized settings.
 * Use with: npm run test:vps
 */

import { defineConfig, devices } from "@playwright/test";
import * as dotenv from "dotenv";
import * as path from "path";

// Load VPS environment
dotenv.config({ path: path.resolve(__dirname, "..", ".env.vps") });
dotenv.config({ path: path.resolve(__dirname, "..", ".env") });

// Force VPS mode
process.env.TEST_ENVIRONMENT = "vps";

/**
 * Parse a numeric environment variable with proper handling of 0 values.
 * Returns the default only when the env var is undefined or not a valid number.
 */
function parseEnvNumber(
  value: string | undefined,
  defaultValue: number,
): number {
  if (value === undefined || value === "") {
    return defaultValue;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? defaultValue : parsed;
}

const baseURL = process.env.BASE_URL || "https://your-vps-hostname.example.com";
const globalTimeout = parseEnvNumber(process.env.TEST_TIMEOUT, 120000);

export default defineConfig({
  testDir: path.resolve(__dirname, "..", "tests"),
  testMatch: "**/*.spec.ts",
  timeout: globalTimeout,
  expect: {
    timeout: 15000,
  },
  fullyParallel: true,
  forbidOnly: true,
  retries: 1,
  workers: 2,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "tests/reports/report.json" }],
    ["junit", { outputFile: "tests/reports/junit-report.xml" }],
  ],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
    headless: true,
    actionTimeout: 30000,
    navigationTimeout: 60000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  globalSetup: path.resolve(__dirname, "..", "vps-setup.ts"),
});

// Re-export constants from vps-helpers.ts for backward compatibility
// The canonical source of truth is in tests/utils/vps-helpers.ts
export {
  getServicesForSuite,
  DEFAULT_PRESERVE_EMBEDDING_MODELS as preserveEmbeddingModels,
  DEFAULT_GPU_INTENSIVE_SERVICES as gpuIntensiveServices,
  EMBEDDING_HOST_SERVICES as embeddingHostServices,
} from "../utils/vps-helpers";
