import { test, expect } from '../../../fixtures/base.fixture';
import { assertAPIResponse } from '../../../utils/assertion-helpers';

test.describe('API Gateway LLM endpoints', () => {
  test('LLM generation works with a simple prompt', async ({ gatewayAPI, testData }) => {
    const prompt = testData.prompts.llm[0];
    const response = await gatewayAPI.generateLLM({ prompt: prompt.prompt });
    assertAPIResponse(response, 'success');
  });

  test('models listing returns a non-empty list', async ({ gatewayAPI }) => {
    const response = await gatewayAPI.listModels();
    assertAPIResponse(response, 'success');
    
    const models = response.data;
    expect(models).toBeDefined();
    expect(Array.isArray(models) ? models.length : 0).toBeGreaterThan(0);
  });
});

