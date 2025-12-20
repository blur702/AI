import { test } from "../../../fixtures/base.fixture";
import { MusicGenPage } from "../../../page-objects/services/MusicGenPage";
import { isServiceAvailable } from "../../../utils/wait-helpers";

test.describe("MusicGen service UI", () => {
  const serviceUrl = process.env.MUSICGEN_URL || "http://localhost:7872";

  test("loads main page", async ({ page }) => {
    const available = await isServiceAvailable(serviceUrl);
    test.skip(!available, `MusicGen service not available at ${serviceUrl}`);
    const ui = new MusicGenPage(page);
    await ui.goto(serviceUrl);
    await ui.waitForPageLoad();
  });
});
