import { test, expect } from "../../../fixtures/base.fixture";

test.describe("Dashboard Backend VRAM API", () => {
  test.describe("GET /api/vram/status", () => {
    test("returns VRAM status with expected GPU schema", async ({
      dashboardAPI,
    }) => {
      const status = await dashboardAPI.getVRAMStatus();

      // GPU info should be present
      expect(status.gpu).toBeTruthy();
      expect(typeof status.gpu.name).toBe("string");
      expect(status.gpu.name.length).toBeGreaterThan(0);

      // Memory values should be numbers
      expect(typeof status.gpu.total_mb).toBe("number");
      expect(typeof status.gpu.used_mb).toBe("number");
      expect(typeof status.gpu.free_mb).toBe("number");
      expect(typeof status.gpu.utilization).toBe("number");

      // Memory values should be reasonable
      expect(status.gpu.total_mb).toBeGreaterThan(0);
      expect(status.gpu.used_mb).toBeGreaterThanOrEqual(0);
      expect(status.gpu.free_mb).toBeGreaterThanOrEqual(0);
      expect(status.gpu.utilization).toBeGreaterThanOrEqual(0);
      expect(status.gpu.utilization).toBeLessThanOrEqual(100);
    });

    test("returns processes array", async ({ dashboardAPI }) => {
      const status = await dashboardAPI.getVRAMStatus();

      expect(Array.isArray(status.processes)).toBe(true);
    });

    test("processes have expected schema when present", async ({
      dashboardAPI,
    }) => {
      const status = await dashboardAPI.getVRAMStatus();

      // If there are processes using GPU, validate their structure
      if (status.processes.length > 0) {
        const process = status.processes[0];
        expect(process).toHaveProperty("pid");
        expect(process).toHaveProperty("name");
        expect(process).toHaveProperty("memory");
      }
    });

    test("used + free memory approximately equals total", async ({
      dashboardAPI,
    }) => {
      const status = await dashboardAPI.getVRAMStatus();

      const calculatedTotal = status.gpu.used_mb + status.gpu.free_mb;
      // Allow 5% tolerance for rounding
      const tolerance = status.gpu.total_mb * 0.05;
      expect(Math.abs(calculatedTotal - status.gpu.total_mb)).toBeLessThan(
        tolerance,
      );
    });

    test("multiple requests return consistent GPU name", async ({
      dashboardAPI,
    }) => {
      const status1 = await dashboardAPI.getVRAMStatus();
      const status2 = await dashboardAPI.getVRAMStatus();

      expect(status1.gpu.name).toBe(status2.gpu.name);
      expect(status1.gpu.total_mb).toBe(status2.gpu.total_mb);
    });
  });
});
