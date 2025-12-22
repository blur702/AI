import { defineConfig, devices } from "@playwright/test";
import * as dotenv from "dotenv";
import * as os from "os";
import * as path from "path";
import { fileURLToPath } from "url";

// ESM equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment-specific config
const envFile = process.env.TEST_ENVIRONMENT === "vps" ? ".env.vps" : ".env";
dotenv.config({ path: path.resolve(__dirname, "..", envFile) });
// Also load base .env as fallback
dotenv.config({ path: path.resolve(__dirname, "..", ".env") });

// Environment detection
export const isCI = !!process.env.CI;
export const isVPS = process.env.TEST_ENVIRONMENT === "vps";

// Default to localhost for local development; override with BASE_URL env var for remote testing
const baseURL = process.env.BASE_URL || "http://localhost";

// Adjust configuration based on environment
const globalTimeout = Number(
  process.env.TEST_TIMEOUT || (isVPS ? 120000 : 60000),
);
const workers = isVPS
  ? 2
  : isCI
    ? 1
    : Math.max(1, Math.floor(os.cpus().length / 2));
const headless = process.env.HEADLESS !== "false";
const retries = isVPS ? 1 : isCI ? 2 : 0;

// Reporter configuration - same reporters for all environments
const reporters: any[] = [
  ["list"],
  ["html", { open: "never", outputFolder: "playwright-report" }],
  ["json", { outputFile: "tests/reports/report.json" }],
  ["junit", { outputFile: "tests/reports/junit-report.xml" }],
];

export default defineConfig({
  testDir: path.resolve(__dirname, "..", "tests"),
  testMatch: "**/*.spec.ts",
  timeout: globalTimeout,
  expect: {
    timeout: isVPS ? 15000 : 10000,
  },
  fullyParallel: true,
  forbidOnly: isCI,
  retries,
  workers,
  reporter: reporters,
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
    headless,
    // Longer action timeout for VPS (network latency)
    actionTimeout: isVPS ? 30000 : 15000,
    // Accept self-signed certificates for external testing
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  // Global setup for VPS environment
  ...(isVPS && {
    globalSetup: path.resolve(__dirname, "..", "vps-setup.ts"),
  }),
});
