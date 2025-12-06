import { BasePage } from '../base/BasePage';

export class Wan2GPPage extends BasePage {
  // Override goto to use domcontentloaded instead of networkidle
  // Gradio UIs maintain persistent WebSocket connections that prevent networkidle
  async goto(url: string): Promise<void> {
    console.log(`[Wan2GPPage] Navigating to ${url}`);
    await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  }

  async waitForPageLoad(): Promise<void> {
    // Wait for Gradio app container to be present
    await this.page.waitForSelector('gradio-app', { timeout: 30000 });
  }
}
