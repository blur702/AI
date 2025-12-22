import { Locator, Page } from "@playwright/test";

export class ServiceCard {
  readonly root: Locator;

  constructor(
    private readonly page: Page,
    rootSelector: string,
  ) {
    this.root = this.page.locator(rootSelector);
  }

  /**
   * Get the status indicator element (.status inside .card-port)
   */
  statusIndicator(): Locator {
    return this.root.locator(".card-port .status");
  }

  /**
   * Get the service name element (.card-title)
   */
  name(): Locator {
    return this.root.locator(".card-title");
  }

  /**
   * Get the service description
   */
  description(): Locator {
    return this.root.locator(".card-description");
  }

  /**
   * Get the port display
   */
  port(): Locator {
    return this.root.locator(".card-port");
  }

  async isVisible(): Promise<boolean> {
    return this.root.isVisible();
  }

  /**
   * Check if service is running (has .status-online indicator)
   */
  async isRunning(): Promise<boolean> {
    const indicator = this.root.locator(".status-online");
    return indicator.isVisible();
  }

  /**
   * Check if service is starting (has .status-starting-indicator)
   */
  async isStarting(): Promise<boolean> {
    const indicator = this.root.locator(".status-starting-indicator");
    return indicator.isVisible();
  }

  /**
   * Click the Open button to open the service in a new tab
   */
  async clickOpen(): Promise<void> {
    const openButton = this.root.locator('.btn-open, button:has-text("Open")');
    await openButton.waitFor({ state: "visible", timeout: 5000 });
    await openButton.click();
  }

  /**
   * Click the Start button to start the service
   */
  async clickStart(): Promise<void> {
    const startButton = this.root.locator(
      '.btn-start, button:has-text("Start")',
    );
    await startButton.waitFor({ state: "visible", timeout: 5000 });
    await startButton.click();
  }

  /**
   * Click the Stop button to stop the service
   */
  async clickStop(): Promise<void> {
    const stopButton = this.root.locator('.btn-stop, button:has-text("Stop")');
    await stopButton.waitFor({ state: "visible", timeout: 5000 });
    await stopButton.click();
  }

  /**
   * Get the start button locator
   */
  startButton(): Locator {
    return this.root.locator('.btn-start, button:has-text("Start")');
  }

  /**
   * Get the stop button locator
   */
  stopButton(): Locator {
    return this.root.locator('.btn-stop, button:has-text("Stop")');
  }

  /**
   * Get the open button locator
   */
  openButton(): Locator {
    return this.root.locator('.btn-open, button:has-text("Open")');
  }

  /**
   * Get the current status class (running, stopped, starting)
   */
  async getStatusClass(): Promise<string> {
    const classes = (await this.root.getAttribute("class")) || "";
    if (classes.includes("status-running")) return "running";
    if (classes.includes("status-starting")) return "starting";
    if (classes.includes("status-stopped")) return "stopped";
    return "unknown";
  }
}
