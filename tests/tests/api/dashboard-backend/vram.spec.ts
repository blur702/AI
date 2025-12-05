import { test, expect } from '../../../fixtures/base.fixture';

test.describe('Dashboard Backend VRAM API', () => {
  test('returns VRAM status with expected schema', async ({ dashboardAPI }) => {
    const status = await dashboardAPI.getVRAMStatus();

    expect(status.gpu).toBeTruthy();
    expect(typeof status.gpu.name).toBe('string');
    expect(typeof status.gpu.total_mb).toBe('number');
    expect(typeof status.gpu.used_mb).toBe('number');
    expect(typeof status.gpu.free_mb).toBe('number');
    expect(typeof status.gpu.utilization).toBe('number');

    expect(Array.isArray(status.processes)).toBe(true);
  });
});
