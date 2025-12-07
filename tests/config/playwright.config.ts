import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as os from 'os';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

const isCI = !!process.env.CI;
// Default to localhost for local development; override with BASE_URL env var for remote testing
const baseURL = process.env.BASE_URL || 'http://localhost';
const globalTimeout = Number(process.env.TEST_TIMEOUT || 60000);
const workers = isCI ? 1 : Math.max(1, Math.floor(os.cpus().length / 2));
const headless = process.env.HEADLESS !== 'false';

export default defineConfig({
  testDir: path.resolve(__dirname, '..', 'tests'),
  testMatch: '**/*.spec.ts',
  timeout: globalTimeout,
  expect: {
    timeout: 10_000
  },
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'tests/reports/report.json' }],
    ['junit', { outputFile: 'tests/reports/junit-report.xml' }]
  ],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
    headless
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] }
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] }
    }
  ]
  // Optionally configure webServer here if you want Playwright
  // to start/stop services automatically before running tests.
});

