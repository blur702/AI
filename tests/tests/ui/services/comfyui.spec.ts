import { test } from "../../../fixtures/services.fixture";
import { ComfyUIPage } from "../../../page-objects/services/ComfyUIPage";

test.describe("ComfyUI service UI", () => {
  test("loads main page", async ({ page, servicesHealthy }) => {
    test.skip(!servicesHealthy, "Services not marked healthy");
    const ui = new ComfyUIPage(page);
    await ui.goto(process.env.COMFYUI_URL || "http://localhost:8188");
    await ui.waitForPageLoad();
  });
});
