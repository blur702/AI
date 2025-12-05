import WebSocket from 'ws';

export interface WebSocketHandle {
  socket: WebSocket;
  messages: any[];
}

export function connectWebSocket(url: string): Promise<WebSocketHandle> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    const messages: any[] = [];

    socket.on('message', (data: WebSocket.RawData) => {
      try {
        messages.push(JSON.parse(data.toString()));
      } catch {
        messages.push(data.toString());
      }
    });

    socket.on('error', (err: Error) => reject(err));

    socket.on('open', () => {
      resolve({ socket, messages });
    });
  });
}

export async function waitForWebSocketMessage(
  handle: WebSocketHandle,
  predicate: (msg: any) => boolean,
  timeoutMs = 30_000
): Promise<any> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const match = handle.messages.find(predicate);
    if (match) {
      return match;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('Timed out waiting for matching WebSocket message');
}

export function closeWebSocket(handle: WebSocketHandle): void {
  handle.socket.close();
}
