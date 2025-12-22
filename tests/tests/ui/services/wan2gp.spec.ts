import { test } from "../../../fixtures/base.fixture";
import { Wan2GPPage } from "../../../page-objects/services/Wan2GPPage";
import { isServiceAvailable } from "../../../utils/wait-helpers";

test.describe("Wan2GP service UI", () => {
  const serviceUrl = process.env.WAN2GP_URL || "http://localhost:7860";

  test("loads main page", async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `Wan2GP service not available at ${serviceUrl}`);
    const ui = new Wan2GPPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
