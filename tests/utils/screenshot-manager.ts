import { Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

export class ScreenshotManager {
  constructor(private readonly baseDir: string) {}

  private buildPath(testName: string, step: string): string {
    const safeTestName = testName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    const safeStep = step.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const dir = path.join(this.baseDir, safeTestName);
    fs.mkdirSync(dir, { recursive: true });
    return path.join(dir, `${timestamp}_${safeStep}.png`);
  }

  async captureScreenshot(page: Page, testName: string, step: string): Promise<string> {
    const filePath = this.buildPath(testName, step);
    await page.screenshot({ path: filePath });
    return filePath;
  }

  async captureFullPage(page: Page, testName: string): Promise<string> {
    const filePath = this.buildPath(testName, 'full-page');
    await page.screenshot({ path: filePath, fullPage: true });
    return filePath;
  }

  // Placeholder for visual regression comparison; implementation can be plugged in later.
  async compareScreenshots(_baseline: string, _current: string): Promise<boolean> {
    throw new Error('compareScreenshots not implemented - visual regression comparison requires implementation');
  }
}
