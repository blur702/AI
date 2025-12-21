// Comprehensive AI Services Test Script using Playwright
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const fs = require("fs");
const path = require("path");
const fs = require("fs");
const path = require("path");

const services = [
  { name: "Open WebUI", url: "http://localhost:3000", expect: "Open WebUI" },
  { name: "ComfyUI", url: "http://localhost:8188", expect: "ComfyUI" },
  { name: "Wan2GP Video", url: "http://localhost:7860", expect: "Wan" },
  { name: "YuE Music", url: "http://localhost:7870", expect: "YuE" },
  { name: "DiffRhythm", url: "http://localhost:7871", expect: "DiffRhythm" },
  { name: "MusicGen", url: "http://localhost:7872", expect: "MusicGen" },
  {
    name: "Stable Audio",
    url: "http://localhost:7873",
    expect: "Stable Audio",
  },
];

async function testService(browser, service) {
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    console.log(`\nTesting ${service.name}...`);
    const response = await page.goto(service.url, {
      timeout: 30000,
      waitUntil: "domcontentloaded",
    });

    if (!response) {
      console.log(`  [FAIL] ${service.name}: No response`);
      return { name: service.name, status: "FAIL", error: "No response" };
    }

    if (response.status() !== 200) {
      console.log(`  [FAIL] ${service.name}: HTTP ${response.status()}`);
      return {
        name: service.name,
        status: "FAIL",
        error: `HTTP ${response.status()}`,
      };
    }

    // Wait a bit for the page to render
    await page.waitForTimeout(2000);

    // Take a screenshot
    const screenshotPath = `D:/AI/screenshots/${service.name.replace(/\s+/g, "_")}.png`;
    await page.screenshot({ path: screenshotPath, fullPage: false });

    // Check page title or content
    const title = await page.title();
    const content = await page.content();

    const hasExpected =
      title.includes(service.expect) || content.includes(service.expect);

    if (hasExpected) {
      console.log(`  [PASS] ${service.name}: Page loaded correctly`);
      return { name: service.name, status: "PASS", title };
    } else {
      console.log(
        `  [WARN] ${service.name}: Page loaded but expected content not found`,
      );
      console.log(`    Title: ${title.substring(0, 50)}`);
      return { name: service.name, status: "WARN", title };
    }
  } catch (error) {
    console.log(`  [FAIL] ${service.name}: ${error.message}`);
    return { name: service.name, status: "FAIL", error: error.message };
  } finally {
    await context.close();
  }
}

async function testOllamaGeneration() {
  console.log("\nTesting Ollama LLM Generation...");
  try {
    const response = await fetch("http://localhost:11434/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "gemma2:27b",
        prompt: 'Say "Hello, test passed!" in exactly those words.',
        stream: false,
      }),
    });

    if (!response.ok) {
      console.log(`  [FAIL] Ollama: HTTP ${response.status}`);
      return {
        name: "Ollama Generation",
        status: "FAIL",
        error: `HTTP ${response.status}`,
      };
    }

    const data = await response.json();
    if (data.response) {
      console.log(`  [PASS] Ollama: Generated response`);
      console.log(`    Response: ${data.response.substring(0, 100)}`);
      return {
        name: "Ollama Generation",
        status: "PASS",
        response: data.response,
      };
    } else {
      console.log(`  [FAIL] Ollama: No response in data`);
      return {
        name: "Ollama Generation",
        status: "FAIL",
        error: "No response",
      };
    }
  } catch (error) {
    console.log(`  [FAIL] Ollama: ${error.message}`);
    return { name: "Ollama Generation", status: "FAIL", error: error.message };
  }
}

async function testOpenWebUIChat(browser) {
  console.log("\nTesting Open WebUI Chat Interface...");
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    await page.goto("http://localhost:3000", { timeout: 30000 });
    await page.waitForTimeout(3000);

    // Check if we can see the chat interface
    const modelSelector =
      (await page.$('[data-testid="model-selector"]')) ||
      (await page.$('button:has-text("Select a model")')) ||
      (await page.$(".model-selector"));

    if (modelSelector) {
      console.log(
        "  [PASS] Open WebUI: Chat interface loaded with model selector",
      );
      return { name: "Open WebUI Chat", status: "PASS" };
    }

    // Alternative check - look for new chat button or similar
    const newChatBtn =
      (await page.$('button:has-text("New Chat")')) ||
      (await page.$('[aria-label="New Chat"]'));

    if (newChatBtn) {
      console.log("  [PASS] Open WebUI: Chat interface loaded");
      return { name: "Open WebUI Chat", status: "PASS" };
    }

    console.log(
      "  [WARN] Open WebUI: Page loaded but chat interface not fully detected",
    );
    return { name: "Open WebUI Chat", status: "WARN" };
  } catch (error) {
    console.log(`  [FAIL] Open WebUI Chat: ${error.message}`);
    return { name: "Open WebUI Chat", status: "FAIL", error: error.message };
  } finally {
    await context.close();
  }
}

async function main() {
  console.log("=".repeat(60));
  console.log("AI Services Verification Test");
  console.log("=".repeat(60));
  console.log(`Test started at: ${new Date().toISOString()}`);

  // Create screenshots directory
  const fs = require("fs");
  if (!fs.existsSync("D:/AI/screenshots")) {
    fs.mkdirSync("D:/AI/screenshots", { recursive: true });
  }

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox"],
  });

  const results = [];

  // Test Ollama first
  results.push(await testOllamaGeneration());

  // Test each service
  for (const service of services) {
    results.push(await testService(browser, service));
  }

  // Test Open WebUI chat specifically
  results.push(await testOpenWebUIChat(browser));

  await browser.close();

  // Summary
  console.log("\n" + "=".repeat(60));
  console.log("TEST SUMMARY");
  console.log("=".repeat(60));

  const passed = results.filter((r) => r.status === "PASS").length;
  const warned = results.filter((r) => r.status === "WARN").length;
  const failed = results.filter((r) => r.status === "FAIL").length;

  results.forEach((r) => {
    const icon =
      r.status === "PASS" ? "[OK]" : r.status === "WARN" ? "[!!]" : "[XX]";
    console.log(`  ${icon} ${r.name}: ${r.status}`);
  });

  console.log("");
  console.log(`Passed: ${passed} | Warnings: ${warned} | Failed: ${failed}`);
  console.log(`Test completed at: ${new Date().toISOString()}`);

  // Write results to file
  fs.writeFileSync("D:/AI/test_results.json", JSON.stringify(results, null, 2));
  console.log("\nResults saved to D:/AI/test_results.json");
  console.log("Screenshots saved to D:/AI/screenshots/");

  process.exit(failed > 0 ? 1 : 0);
}

main().catch(console.error);
