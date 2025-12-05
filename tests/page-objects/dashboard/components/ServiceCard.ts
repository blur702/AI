import { Locator, Page } from '@playwright/test';

export class ServiceCard {
  readonly root: Locator;

  constructor(private readonly page: Page, rootSelector: string) {
    this.root = this.page.locator(rootSelector);
  }

  statusIndicator(): Locator {
    return this.root.locator('.service-status');
  }

  name(): Locator {
    return this.root.locator('.service-name');
  }

  async isVisible(): Promise<boolean> {
    return this.root.isVisible();
  }
}

