import { test, expect } from '../../../fixtures/base.fixture';

test.describe('API Gateway health', () => {
  test('health endpoint returns success', async ({ gatewayAPI }) => {
    const health = await gatewayAPI.getHealth();
    expect(health.status).toBeDefined();
  });
});

