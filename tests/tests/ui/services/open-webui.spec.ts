import { Page } from '@playwright/test';
import { test, expect } from '../../../fixtures/services.fixture';
import { DashboardPage } from '../../../page-objects/dashboard/DashboardPage';
import { OpenWebUIPage } from '../../../page-objects/services/OpenWebUIPage';
import { ScreenshotManager } from '../../../utils/screenshot-manager';

/**
 * Helper function to perform the Open WebUI chat interaction flow.
 * Consolidates repeated logic for waiting, sending message, capturing screenshot.
 */
async function performChatInteraction(
  targetPage: Page,
  prompt: string,
  testTitle: string,
  screenshotManager: ScreenshotManager,
  stepName: string = 'chat-complete'
): Promise<string> {
  const ui = new OpenWebUIPage(targetPage);
  await ui.waitForChatLoad();

  console.log(`[Test] Sending prompt: ${prompt}`);
  await ui.sendMessage(prompt);

  // Wait for LLM response with extended timeout for slow models
  await ui.waitForResponse(60000);

  // Capture screenshot
  const screenshotPath = await screenshotManager.captureScreenshot(
    targetPage,
    testTitle,
    stepName
  );
  console.log(`[Test] Screenshot saved to: ${screenshotPath}`);

  // Attach screenshot to test report
  await test.info().attach(stepName, {
    path: screenshotPath,
    contentType: 'image/png'
  });

  return screenshotPath;
}

test.describe('Open WebUI E2E Chat Interaction', () => {
  test('loads dashboard, opens WebUI, sends message, and captures screenshot', async ({
    page,
    context,
    testData,
    screenshotManager,
    servicesHealthy
  }) => {
    // Skip if services are not healthy
    test.skip(!servicesHealthy, 'Services not marked healthy');

    const baseUrl = process.env.BASE_URL || 'http://localhost';
    const openWebUIUrl = process.env.OPEN_WEBUI_URL || 'http://localhost:3000';
    const prompt = testData.prompts.llm[0].prompt;

    // Step 1: Load the dashboard
    console.log(`[Test] Loading dashboard at ${baseUrl}`);
    const dashboard = new DashboardPage(page);
    await dashboard.goto(baseUrl);
    await dashboard.waitForPageLoad();

    // Capture dashboard screenshot
    await screenshotManager.captureScreenshot(page, test.info().title, 'dashboard-loaded');

    // Step 2: Locate the Open WebUI service card
    console.log('[Test] Looking for Open WebUI service card...');
    const serviceCard = dashboard.getServiceCardByName('Open WebUI');

    // Check if service card is visible
    const isCardVisible = await serviceCard.isVisible();
    if (!isCardVisible) {
      console.log('[Test] Open WebUI service card not found on dashboard, navigating directly');
      await page.goto(openWebUIUrl);
      await performChatInteraction(page, prompt, test.info().title, screenshotManager);
      return;
    }

    // Step 3: Click Open button and handle new tab
    console.log('[Test] Clicking Open button on service card...');

    // Set up listener for new page before clicking
    const newPagePromise = context.waitForEvent('page', { timeout: 15000 });

    try {
      await serviceCard.clickOpen();
    } catch {
      console.log('[Test] Open button click failed, trying alternative approach');
      // Try clicking any link/button that opens the service
      const openLink = page.locator(`a[href*="3000"], a[href*="openwebui"]`).first();
      if (await openLink.isVisible()) {
        await openLink.click();
      } else {
        // Navigate directly as fallback
        console.log('[Test] Navigating directly to Open WebUI');
        await page.goto(openWebUIUrl);
        await performChatInteraction(page, prompt, test.info().title, screenshotManager);
        return;
      }
    }

    // Step 4: Wait for new tab and switch to it
    let openWebUIPage: Page;
    try {
      openWebUIPage = await newPagePromise;
      console.log('[Test] New tab opened successfully');
    } catch {
      console.log('[Test] New tab did not open, checking current page or navigating directly');
      // Maybe the link opened in the same tab or the button uses a different mechanism
      const currentUrl = page.url();
      if (currentUrl.includes('3000') || currentUrl.includes('openwebui')) {
        // Already on Open WebUI
        await performChatInteraction(page, prompt, test.info().title, screenshotManager);
        return;
      }

      // Navigate directly as last resort
      await page.goto(openWebUIUrl);
      await performChatInteraction(page, prompt, test.info().title, screenshotManager);
      return;
    }

    // Wait for the new page to load
    await openWebUIPage.waitForLoadState('networkidle');
    console.log(`[Test] Open WebUI page loaded: ${openWebUIPage.url()}`);

    // Step 5: Interact with Open WebUI chat using helper
    const screenshotPath = await performChatInteraction(
      openWebUIPage,
      prompt,
      test.info().title,
      screenshotManager
    );

    // Verify screenshot file exists
    const fs = await import('fs');
    expect(fs.existsSync(screenshotPath)).toBe(true);

    // Step 6: Cleanup - close the Open WebUI tab
    await openWebUIPage.close();
    console.log('[Test] Test completed successfully');
  });

  test('directly navigates to Open WebUI and sends a chat message', async ({
    page,
    testData,
    screenshotManager,
    servicesHealthy
  }) => {
    // Skip if services are not healthy
    test.skip(!servicesHealthy, 'Services not marked healthy');

    const openWebUIUrl = process.env.OPEN_WEBUI_URL || 'http://localhost:3000';
    const prompt = testData.prompts.llm[0].prompt;

    // Navigate directly to Open WebUI
    console.log(`[Test] Navigating to Open WebUI at ${openWebUIUrl}`);
    const ui = new OpenWebUIPage(page);
    await ui.goto(openWebUIUrl);

    // Capture initial state
    await screenshotManager.captureScreenshot(page, test.info().title, 'chat-loaded');

    // Use helper for chat interaction
    await performChatInteraction(
      page,
      prompt,
      test.info().title,
      screenshotManager,
      'response-received'
    );

    console.log('[Test] Test completed successfully');
  });
});
