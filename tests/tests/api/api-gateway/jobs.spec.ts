import { test, expect } from '../../../fixtures/base.fixture';

test.describe('API Gateway job management', () => {
  test('job listing works', async ({ gatewayAPI }) => {
    const response = await gatewayAPI.listJobs(0, 5);
    expect(response.success).toBe(true);
  });
});

