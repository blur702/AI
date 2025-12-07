import { test, expect } from '../../../fixtures/base.fixture';

test.describe('API Gateway health', () => {
  test('health endpoint returns success', async ({ gatewayAPI }) => {
    try {
      const health = await gatewayAPI.getHealth();
      expect(health.success).toBe(true);
    } catch (error: any) {
      // Skip test if gateway is not running (ECONNREFUSED)
      if (error.code === 'ECONNREFUSED' || error.message?.includes('ECONNREFUSED')) {
        test.skip(true, 'API Gateway is not running (port 1301)');
        return;
      }
      throw error;
    }
  });
});

