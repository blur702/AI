import { test } from "../../../fixtures/base.fixture";
import { N8NPage } from "../../../page-objects/services/N8NPage";
import { isServiceAvailable } from "../../../utils/wait-helpers";

test.describe("N8N service UI", () => {
  const serviceUrl = process.env.N8N_URL || "http://localhost:5678";

  test("loads main page", async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `N8N service not available at ${serviceUrl}`);
    const ui = new N8NPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
