import { test, expect } from '../../../fixtures/base.fixture';

test.describe('Dashboard model management', () => {
  test('lists Ollama models (placeholder)', async ({ dashboardAPI }) => {
    const models = await dashboardAPI.listOllamaModels();
    expect(Array.isArray(models)).toBe(true);
  });
});

