import { Locator, Page } from '@playwright/test';
import { BasePage } from '../base/BasePage';

export class OpenWebUIPage extends BasePage {
  // Track the count of assistant messages before sending
  private assistantMessageCountBeforeSend: number = 0;

  constructor(page: Page) {
    super(page);
  }

  /**
   * Wait for the chat interface to fully load
   */
  async waitForChatLoad(timeoutMs = 15000): Promise<void> {
    try {
      console.log('[OpenWebUIPage] Waiting for chat interface to load...');
      // Wait for the main chat container to be visible
      // Open WebUI uses various container selectors depending on version
      await this.page.waitForSelector(
        'textarea, [contenteditable="true"], input[type="text"]',
        { timeout: timeoutMs, state: 'visible' }
      );
      // Wait for network to settle
      await this.page.waitForLoadState('networkidle', { timeout: timeoutMs });
      console.log('[OpenWebUIPage] Chat interface loaded');
    } catch (error) {
      console.error('[OpenWebUIPage] Failed to load chat interface', error);
      throw error;
    }
  }

  /**
   * Get the chat input locator
   * Tries multiple selectors to find the message input, including contenteditable elements
   */
  getChatInput(): Locator {
    // Open WebUI can use textarea or contenteditable for chat input
    // Try multiple selectors for compatibility
    return this.page.locator([
      // Textarea-based inputs
      'textarea[placeholder*="message" i]',
      'textarea[placeholder*="Send" i]',
      'textarea[placeholder*="Ask" i]',
      '#chat-textarea',
      '[data-testid="message-input"]',
      'textarea.w-full',
      'textarea',
      // Contenteditable-based inputs
      'div[contenteditable="true"][data-testid="message-input"]',
      'div[contenteditable="true"][placeholder*="message" i]',
      'div[contenteditable="true"][role="textbox"]',
      '[contenteditable="true"].chat-input',
      '[contenteditable="true"]'
    ].join(', ')).first();
  }

  /**
   * Get the locator for assistant messages
   */
  private getAssistantMessagesLocator(): Locator {
    // Open WebUI shows assistant messages in various containers
    return this.page.locator([
      '[data-role="assistant"]',
      '.message.assistant',
      '.assistant-message',
      '[data-message-role="assistant"]',
      '.chat-message[data-role="assistant"]'
    ].join(', '));
  }

  /**
   * Get the current count of assistant messages
   */
  private async getAssistantMessageCount(): Promise<number> {
    const messages = this.getAssistantMessagesLocator();
    return messages.count();
  }

  /**
   * Send a message in the chat
   */
  async sendMessage(text: string): Promise<void> {
    try {
      console.log(`[OpenWebUIPage] Sending message: ${text.substring(0, 50)}...`);

      // Record the count of assistant messages before sending
      this.assistantMessageCountBeforeSend = await this.getAssistantMessageCount();
      console.log(`[OpenWebUIPage] Assistant messages before send: ${this.assistantMessageCountBeforeSend}`);

      const input = this.getChatInput();
      await input.waitFor({ state: 'visible', timeout: 10000 });

      // Check if it's a contenteditable element
      const tagName = await input.evaluate(el => el.tagName.toLowerCase());
      const isContentEditable = await input.evaluate(el => el.getAttribute('contenteditable') === 'true');

      if (isContentEditable || tagName === 'div') {
        // For contenteditable, we need to use type() or set innerHTML
        await input.click();
        await input.fill(''); // Clear first
        await this.page.keyboard.type(text);
      } else {
        // For textarea/input, use fill()
        await input.fill(text);
      }

      // Press Enter to send (Open WebUI uses Enter to submit)
      await input.press('Enter');
      // Wait a moment for the message to be sent
      await this.page.waitForTimeout(500);
      console.log('[OpenWebUIPage] Message sent');
    } catch (error) {
      console.error('[OpenWebUIPage] Failed to send message', error);
      throw error;
    }
  }

  /**
   * Wait for the LLM response to appear and complete.
   * Anchors detection to a new response created after the message was sent.
   */
  async waitForLLMResponse(timeoutMs = 30000): Promise<void> {
    try {
      console.log('[OpenWebUIPage] Waiting for LLM response...');

      const startTime = Date.now();
      const expectedCount = this.assistantMessageCountBeforeSend + 1;

      // Wait for a new assistant message to appear (count increases)
      await this.page.waitForFunction(
        ({ selector, expectedCount }) => {
          const messages = document.querySelectorAll(selector);
          return messages.length >= expectedCount;
        },
        {
          selector: [
            '[data-role="assistant"]',
            '.message.assistant',
            '.assistant-message',
            '[data-message-role="assistant"]',
            '.chat-message[data-role="assistant"]'
          ].join(', '),
          expectedCount
        },
        { timeout: timeoutMs }
      );

      console.log('[OpenWebUIPage] New assistant message detected');

      // Get the newly added assistant message (the one at index = countBefore)
      const assistantMessages = this.getAssistantMessagesLocator();
      const newMessage = assistantMessages.nth(this.assistantMessageCountBeforeSend);

      // Wait for streaming to complete by checking for loading indicators to disappear
      const loadingSelectors = [
        '.loading',
        '[class*="loading"]',
        '.animate-pulse',
        '.typing-indicator',
        'svg.animate-spin',
        '[data-loading="true"]'
      ].join(', ');

      // Give some time for response to start streaming
      await this.page.waitForTimeout(1000);

      // Wait for loading indicators within the new message to disappear
      const remainingTime = Math.max(timeoutMs - (Date.now() - startTime) - 2000, 5000);
      try {
        // Check if there are any loading indicators scoped to the new message
        const loadingIndicator = newMessage.locator(loadingSelectors).first();
        if (await loadingIndicator.isVisible({ timeout: 1000 }).catch(() => false)) {
          await loadingIndicator.waitFor({
            state: 'hidden',
            timeout: remainingTime
          });
        }
      } catch {
        // No loading indicator found or already hidden - that's fine
      }

      // Additional wait for response text to stabilize (no more streaming)
      await this.waitForTextStable(newMessage, 3000);

      console.log('[OpenWebUIPage] LLM response received and stable');
    } catch (error) {
      console.error('[OpenWebUIPage] Failed to receive LLM response', error);
      throw error;
    }
  }

  /**
   * Wait for the text content of an element to stabilize (stop changing)
   * @param locator - The element to monitor
   * @param stabilityTimeMs - Duration of stability required (default: 2000ms)
   * @param overallTimeoutMs - Maximum time to wait before timing out (default: 60000ms)
   * @throws Error if text does not stabilize within the overall timeout
   */
  private async waitForTextStable(
    locator: Locator,
    stabilityTimeMs = 2000,
    overallTimeoutMs = 60000
  ): Promise<void> {
    const deadline = Date.now() + overallTimeoutMs;
    let previousText = '';
    let stableStartTime = Date.now();

    while (Date.now() - stableStartTime < stabilityTimeMs) {
      if (Date.now() > deadline) {
        throw new Error(
          `Text did not stabilize within ${overallTimeoutMs}ms. Last text: "${previousText.substring(0, 100)}..."`
        );
      }

      const currentText = await locator.textContent() || '';
      if (currentText !== previousText) {
        previousText = currentText;
        stableStartTime = Date.now();
      }
      await this.page.waitForTimeout(200);
    }
  }

  /**
   * Get the last response message text
   */
  async getLastResponseText(): Promise<string> {
    const assistantMessages = this.getAssistantMessagesLocator();
    const count = await assistantMessages.count();
    if (count === 0) {
      return '';
    }
    const lastMessage = assistantMessages.nth(count - 1);
    return (await lastMessage.textContent()) || '';
  }
}
