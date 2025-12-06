import { test, expect } from '../../../fixtures/base.fixture';
import { assertAPIResponse } from '../../../utils/assertion-helpers';

test.describe('API Gateway LLM endpoints', () => {
  // Skip: This test requires API key authentication and running Ollama service
  test.skip('LLM generation works with a simple prompt', async ({ gatewayAPI, testData }) => {
    const prompt = testData.prompts.llm[0];
    const response = await gatewayAPI.generateLLM({ prompt: prompt.prompt });
    assertAPIResponse(response, 'success');
  });

  test('models listing returns a valid response', async ({ gatewayAPI }) => {
    const response = await gatewayAPI.listModels();
    assertAPIResponse(response, 'success');

    const data = response.data;
    expect(data).toBeDefined();
    expect(data.models).toBeDefined();
    expect(Array.isArray(data.models)).toBe(true);
  });
});

