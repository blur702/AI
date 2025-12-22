import { Locator, Page } from "@playwright/test";

export class VRAMMonitor {
  private readonly root: Locator;

  constructor(
    private readonly page: Page,
    rootSelector: string,
  ) {
    this.root = this.page.locator(rootSelector);
  }

  usageBar(): Locator {
    return this.root.locator(".vram-usage-bar");
  }

  usageText(): Locator {
    return this.root.locator(".vram-usage-text");
  }
}
