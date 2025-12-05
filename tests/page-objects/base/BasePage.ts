import { expect, Page, Response } from '@playwright/test';

export class BasePage {
  protected readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto(url: string): Promise<void> {
    try {
      console.log(`[BasePage] Navigating to ${url}`);
      await this.page.goto(url, { waitUntil: 'networkidle' });
    } catch (error) {
      console.error(`[BasePage] Failed to navigate to ${url}`, error);
      throw error;
    }
  }

  async waitForPageLoad(): Promise<void> {
    try {
      await this.page.waitForLoadState('networkidle');
    } catch (error) {
      console.error('[BasePage] Error waiting for page load', error);
      throw error;
    }
  }

  async getTitle(): Promise<string> {
    return this.page.title();
  }

  async getURL(): Promise<string> {
    return this.page.url();
  }

  async clickElement(selector: string): Promise<void> {
    try {
      await this.page.click(selector);
    } catch (error) {
      console.error(`[BasePage] Error clicking element: ${selector}`, error);
      throw error;
    }
  }

  async fillInput(selector: string, value: string): Promise<void> {
    try {
      await this.page.fill(selector, value);
    } catch (error) {
      console.error(`[BasePage] Error filling input ${selector} with value ${value}`, error);
      throw error;
    }
  }

  async selectOption(selector: string, value: string): Promise<void> {
    try {
      await this.page.selectOption(selector, value);
    } catch (error) {
      console.error(`[BasePage] Error selecting option ${value} on ${selector}`, error);
      throw error;
    }
  }

  async waitForSelector(selector: string, timeout = 10_000): Promise<void> {
    try {
      await this.page.waitForSelector(selector, { timeout });
    } catch (error) {
      console.error(`[BasePage] Error waiting for selector: ${selector}`, error);
      throw error;
    }
  }

  async waitForNavigation(): Promise<void> {
    try {
      await this.page.waitForLoadState('load');
    } catch (error) {
      console.error('[BasePage] Error waiting for navigation', error);
      throw error;
    }
  }

  async waitForResponse(urlPattern: RegExp | string, timeout = 10_000): Promise<Response> {
    try {
      const response = await this.page.waitForResponse(
        (res) => (typeof urlPattern === 'string' ? res.url().includes(urlPattern) : urlPattern.test(res.url())),
        { timeout }
      );
      return response;
    } catch (error) {
      console.error('[BasePage] Error waiting for response', error);
      throw error;
    }
  }

  async expectVisible(selector: string): Promise<void> {
    await expect(this.page.locator(selector)).toBeVisible();
  }

  async expectText(selector: string, text: string | RegExp): Promise<void> {
    await expect(this.page.locator(selector)).toHaveText(text);
  }

  async expectURL(pattern: RegExp | string): Promise<void> {
    await expect(this.page).toHaveURL(pattern);
  }
}
