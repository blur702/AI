import { test } from "../../../fixtures/services.fixture";
import { OllamaPage } from "../../../page-objects/services/OllamaPage";

test.describe("Ollama service UI", () => {
  test("loads main page", async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, "Services not marked healthy");
    const ui = new OllamaPage(page);
    await ui.goto(process.env.OLLAMA_URL || "http://localhost:11434");
    await ui.waitForPageLoad();
  });
});
