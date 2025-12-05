import { test, expect } from '../../../fixtures/base.fixture';

test.describe('Model switching (placeholder)', () => {
  test('lists models and can load one', async ({ dashboardAPI, testData }) => {
    const models = await dashboardAPI.listOllamaModels();
    expect(Array.isArray(models)).toBe(true);

    const target = testData.models.ollamaModels[0];
    await dashboardAPI.loadModel(target.name);
  });
});
