import { test, expect } from '../../../fixtures/base.fixture';
import { connectWebSocket, closeWebSocket, waitForWebSocketMessage } from '../../../utils/websocket-helper';

test.describe('API Gateway WebSocket', () => {
  test('job WebSocket connects and receives messages (placeholder)', async () => {
    const wsUrl = process.env.GATEWAY_WS_URL;
    if (!wsUrl) {
      test.skip(true, 'GATEWAY_WS_URL not configured');
    }

    const handle = await connectWebSocket(wsUrl as string);
    await expect(async () => {
      await waitForWebSocketMessage(handle, () => true, 5_000);
    }).resolves.not.toThrow();
    closeWebSocket(handle);
  });
});
