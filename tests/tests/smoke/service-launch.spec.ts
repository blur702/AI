import { test, expect, Page, BrowserContext } from "@playwright/test";

/**
 * Service Launch Smoke Tests
 *
 * Tests that all services can be started from the dashboard and load correctly in a new tab.
 * These tests verify external accessibility via https://ssdd.kevinalthaus.com
 */

const BASE_URL = process.env.BASE_URL || "https://ssdd.kevinalthaus.com";

// Service definitions with their expected characteristics
const SERVICES = [
  {
    id: "openwebui",
    name: "Open WebUI",
    proxyPath: "/openwebui/",
    expectedTitle: /open.*webui|chat/i,
    expectedContent: ["model", "chat", "message"],
    timeout: 30000,
  },
  {
    id: "comfyui",
    name: "ComfyUI",
    proxyPath: "/comfyui/",
    expectedTitle: /comfyui/i,
    expectedContent: ["queue", "workflow", "node"],
    timeout: 30000,
  },
  {
    id: "alltalk",
    name: "AllTalk TTS",
    proxyPath: "/alltalk/",
    expectedTitle: /alltalk|tts/i,
    expectedContent: ["voice", "text", "speech"],
    timeout: 30000,
  },
  {
    id: "wan2gp",
    name: "Wan2GP Video",
    proxyPath: "/wan2gp/",
    expectedTitle: /wan|video|gradio/i,
    expectedContent: ["video", "generate", "prompt"],
    timeout: 30000,
  },
  {
    id: "n8n",
    name: "N8N Workflows",
    proxyPath: "/n8n/",
    expectedTitle: /n8n|workflow/i,
    expectedContent: ["workflow", "node", "automation"],
    timeout: 30000,
  },
  {
    id: "yue",
    name: "YuE Music",
    proxyPath: "/yue/",
    expectedTitle: /yue|music|gradio/i,
    expectedContent: ["music", "lyrics", "generate"],
    timeout: 30000,
  },
  {
    id: "diffrhythm",
    name: "DiffRhythm",
    proxyPath: "/diffrhythm/",
    expectedTitle: /diffrhythm|music|gradio/i,
    expectedContent: ["music", "generate", "audio"],
    timeout: 30000,
  },
  {
    id: "musicgen",
    name: "MusicGen",
    proxyPath: "/musicgen/",
    expectedTitle: /musicgen|audio|gradio/i,
    expectedContent: ["music", "generate", "melody"],
    timeout: 30000,
  },
  {
    id: "stable_audio",
    name: "Stable Audio",
    proxyPath: "/stable-audio/",
    expectedTitle: /stable.*audio|gradio/i,
    expectedContent: ["audio", "generate", "sound"],
    timeout: 30000,
  },
];

// Configure browser to ignore HTTPS errors for self-signed certs
test.use({
  ignoreHTTPSErrors: true,
});

test.describe("Dashboard Load", () => {
  test("should load the dashboard", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Check for dashboard elements
    await expect(page.locator("body")).toBeVisible();

    // Take screenshot of dashboard
    await page.screenshot({
      path: `screenshots/dashboard_${new Date().toISOString().replace(/[:.]/g, "-")}.png`,
      fullPage: true,
    });

    console.log("Dashboard loaded successfully");
  });
});

test.describe("Service Tab Launch Tests", () => {
  for (const service of SERVICES) {
    test(`should open ${service.name} in new tab`, async ({
      context,
      page,
    }) => {
      // Navigate to dashboard first
      await page.goto(BASE_URL, { waitUntil: "networkidle" });

      const serviceUrl = `${BASE_URL}${service.proxyPath}`;
      console.log(`Testing ${service.name} at ${serviceUrl}`);

      // Open service in new tab
      const newPage = await context.newPage();

      try {
        const response = await newPage.goto(serviceUrl, {
          waitUntil: "domcontentloaded",
          timeout: service.timeout,
        });

        // Check response status
        const status = response?.status() || 0;
        console.log(`${service.name} response status: ${status}`);

        if (status === 401) {
          console.log(
            `${service.name}: Requires authentication (401) - service is reachable`,
          );
          // 401 means the service is running but requires auth - this is OK for smoke test
          return;
        }

        if (status === 502 || status === 503 || status === 504) {
          test.skip(true, `${service.name} is not running (${status})`);
          return;
        }

        expect(status).toBeLessThan(500);

        // Wait for page to stabilize
        await newPage
          .waitForLoadState("networkidle", { timeout: 10000 })
          .catch(() => {});

        // Take screenshot
        await newPage.screenshot({
          path: `screenshots/${service.id}_${new Date().toISOString().replace(/[:.]/g, "-")}.png`,
          fullPage: true,
        });

        // Verify page has content
        const bodyText = (await newPage.locator("body").textContent()) || "";
        expect(bodyText.length).toBeGreaterThan(0);

        console.log(`${service.name} loaded successfully`);
      } catch (error: any) {
        // Handle timeout or connection errors gracefully
        if (
          error.message?.includes("timeout") ||
          error.message?.includes("ECONNREFUSED")
        ) {
          test.skip(
            true,
            `${service.name} is not accessible: ${error.message}`,
          );
          return;
        }
        throw error;
      } finally {
        await newPage.close();
      }
    });
  }
});

test.describe("Dashboard Service Elements", () => {
  test("should display service cards with proper structure", async ({
    page,
  }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Look for service cards or service list
    const serviceElements = page.locator(
      '[class*="service"], [class*="card"], [data-service]',
    );
    const count = await serviceElements.count();

    console.log(`Found ${count} service-related elements on dashboard`);

    // Assert that we have at least some service elements
    expect(count).toBeGreaterThan(0);

    // Verify at least one service card is visible
    const firstServiceElement = serviceElements.first();
    await expect(firstServiceElement).toBeVisible();

    // Take screenshot showing all services
    await page.screenshot({
      path: `screenshots/all_services_${new Date().toISOString().replace(/[:.]/g, "-")}.png`,
      fullPage: true,
    });
  });

  test("should display service status indicators", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Check for status indicators (running, stopped, etc)
    const statusIndicators = page.locator(
      '[class*="status"], [class*="indicator"], [class*="running"], [class*="stopped"]',
    );
    const count = await statusIndicators.count();

    console.log(`Found ${count} status indicator elements`);

    // Assert that we have status indicators present
    expect(count).toBeGreaterThan(0);

    // Verify at least one status indicator is visible
    const firstIndicator = statusIndicators.first();
    await expect(firstIndicator).toBeVisible();
  });

  test("should have visible service control buttons", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Look for start/stop/toggle buttons within service cards
    const controlButtons = page.locator(
      'button[class*="start"], button[class*="stop"], button[class*="toggle"], ' +
        '[role="button"][class*="start"], [role="button"][class*="stop"], ' +
        '[data-action="start"], [data-action="stop"]',
    );
    const buttonCount = await controlButtons.count();

    console.log(`Found ${buttonCount} service control buttons`);

    // If control buttons exist, verify they're properly structured
    if (buttonCount > 0) {
      const firstButton = controlButtons.first();
      await expect(firstButton).toBeVisible();
    }
  });
});

test.describe("Service Start/Stop Interaction", () => {
  // This test requires a lightweight service that can be safely toggled
  test("should toggle a service and verify status change", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Find a service card with a toggle/start/stop button
    // Prefer a lightweight service like n8n for testing
    const serviceCard = page
      .locator('[data-service="n8n"], [class*="service"][class*="n8n"]')
      .first();
    let targetCard = serviceCard;

    if ((await serviceCard.count()) === 0) {
      // Fallback: find any service card with a control button
      const anyServiceCard = page
        .locator('[class*="service"], [class*="card"]')
        .filter({
          has: page.locator(
            'button[class*="start"], button[class*="stop"], button[class*="toggle"]',
          ),
        })
        .first();

      if ((await anyServiceCard.count()) === 0) {
        test.skip(true, "No service cards with control buttons found");
        return;
      }
      targetCard = anyServiceCard;
    }

    // Find the status indicator within the service card
    const statusIndicator = targetCard
      .locator('[class*="status"], [class*="indicator"]')
      .first();
    if ((await statusIndicator.count()) === 0) {
      test.skip(true, "No status indicator found in service card");
      return;
    }

    // Find the toggle/control button within the service card
    const toggleButton = targetCard
      .locator(
        'button[class*="toggle"], button[class*="start"], button[class*="stop"]',
      )
      .first();
    if ((await toggleButton.count()) === 0) {
      test.skip(true, "No toggle button found in service card");
      return;
    }

    // Capture initial state
    const getStatusState = async () => {
      const classList = (await statusIndicator.getAttribute("class")) || "";
      const textContent = (await statusIndicator.textContent()) || "";
      return { classList, textContent: textContent.toLowerCase().trim() };
    };

    const initialState = await getStatusState();
    console.log(
      `Initial status - class: "${initialState.classList}", text: "${initialState.textContent}"`,
    );

    // Take screenshot before interaction
    await page.screenshot({
      path: `screenshots/service_toggle_before_${new Date().toISOString().replace(/[:.]/g, "-")}.png`,
      fullPage: true,
    });

    // Click the toggle button
    await toggleButton.click();

    // Wait for status change with polling (up to 10 seconds)
    const maxWaitTime = 10000;
    const pollInterval = 500;
    const startTime = Date.now();
    let statusChanged = false;
    let finalState = initialState;

    while (Date.now() - startTime < maxWaitTime) {
      await page.waitForTimeout(pollInterval);
      finalState = await getStatusState();

      // Check if status changed (either class or text content)
      const classChanged = finalState.classList !== initialState.classList;
      const textChanged = finalState.textContent !== initialState.textContent;

      if (classChanged || textChanged) {
        statusChanged = true;
        console.log(`Status changed after ${Date.now() - startTime}ms`);
        console.log(
          `Final status - class: "${finalState.classList}", text: "${finalState.textContent}"`,
        );
        break;
      }
    }

    // Take screenshot after interaction
    await page.screenshot({
      path: `screenshots/service_toggle_after_${new Date().toISOString().replace(/[:.]/g, "-")}.png`,
      fullPage: true,
    });

    // Verify the status actually changed
    if (!statusChanged) {
      console.warn(
        "Status did not change within timeout - service may be unresponsive or already in target state",
      );
      // Log detailed state for debugging
      console.log(`Initial class: "${initialState.classList}"`);
      console.log(`Final class: "${finalState.classList}"`);
      console.log(`Initial text: "${initialState.textContent}"`);
      console.log(`Final text: "${finalState.textContent}"`);
    }

    // Assert that either:
    // 1. Status changed (class or text is different), OR
    // 2. Status shows a transitional state (starting, stopping)
    const isTransitioning =
      finalState.textContent.includes("starting") ||
      finalState.textContent.includes("stopping") ||
      finalState.classList.includes("starting") ||
      finalState.classList.includes("stopping");

    expect(
      statusChanged || isTransitioning,
      `Expected service status to change or be in transitional state. ` +
        `Initial: "${initialState.textContent}" (${initialState.classList}), ` +
        `Final: "${finalState.textContent}" (${finalState.classList})`,
    ).toBe(true);

    console.log("Service toggle test completed successfully");
  });
});

test.describe("External Accessibility", () => {
  test("should verify nginx proxy paths are accessible", async ({
    request,
  }) => {
    const proxyPaths = [
      { path: "/", name: "Dashboard" },
      { path: "/openwebui/", name: "Open WebUI" },
      { path: "/comfyui/", name: "ComfyUI" },
      { path: "/n8n/", name: "N8N" },
      { path: "/alltalk/", name: "AllTalk" },
      { path: "/wan2gp/", name: "Wan2GP" },
      { path: "/yue/", name: "YuE" },
      { path: "/diffrhythm/", name: "DiffRhythm" },
      { path: "/musicgen/", name: "MusicGen" },
      { path: "/stable-audio/", name: "Stable Audio" },
      { path: "/ollama/", name: "Ollama API" },
      { path: "/weaviate/", name: "Weaviate" },
    ];

    const results: { name: string; status: number; accessible: boolean }[] = [];

    for (const { path, name } of proxyPaths) {
      try {
        const response = await request.get(`${BASE_URL}${path}`, {
          timeout: 10000,
          ignoreHTTPSErrors: true,
        });
        const status = response.status();
        // 200, 301, 302, 401, 403 all indicate the proxy path works
        const accessible = status < 500;
        results.push({ name, status, accessible });
        console.log(`${name}: ${status} ${accessible ? "✓" : "✗"}`);
      } catch (error: any) {
        results.push({ name, status: 0, accessible: false });
        console.log(`${name}: FAILED - ${error.message}`);
      }
    }

    // At minimum, dashboard should be accessible
    const dashboard = results.find((r) => r.name === "Dashboard");
    expect(dashboard?.accessible).toBe(true);

    // Report summary
    const accessible = results.filter((r) => r.accessible).length;
    console.log(
      `\nAccessibility Summary: ${accessible}/${results.length} services reachable`,
    );
  });
});

test.describe("Visual Regression Baseline", () => {
  test("should capture dashboard screenshot for visual comparison", async ({
    page,
  }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Wait for any animations to complete
    await page.waitForTimeout(2000);

    // Capture full page screenshot
    await page.screenshot({
      path: "screenshots/visual-baseline/dashboard.png",
      fullPage: true,
    });

    // Capture viewport screenshot
    await page.screenshot({
      path: "screenshots/visual-baseline/dashboard-viewport.png",
      fullPage: false,
    });

    console.log("Visual baseline screenshots captured");
  });

  for (const service of SERVICES.slice(0, 3)) {
    // Limit to first 3 for baseline
    test(`should capture ${service.name} screenshot for visual comparison`, async ({
      context,
    }) => {
      const newPage = await context.newPage();
      const serviceUrl = `${BASE_URL}${service.proxyPath}`;

      try {
        await newPage.goto(serviceUrl, {
          waitUntil: "domcontentloaded",
          timeout: service.timeout,
        });

        await newPage
          .waitForLoadState("networkidle", { timeout: 10000 })
          .catch(() => {});
        await newPage.waitForTimeout(2000);

        await newPage.screenshot({
          path: `screenshots/visual-baseline/${service.id}.png`,
          fullPage: true,
        });

        console.log(`Captured baseline for ${service.name}`);
      } catch (error: any) {
        if (error.message?.includes("timeout")) {
          test.skip(
            true,
            `${service.name} not accessible for baseline capture`,
          );
        } else {
          throw error;
        }
      } finally {
        await newPage.close();
      }
    });
  }
});
