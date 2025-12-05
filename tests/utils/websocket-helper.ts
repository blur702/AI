import WebSocket from 'ws';

export interface WebSocketHandle {
  socket: WebSocket;
  messages: any[];
}

export function connectWebSocket(url: string): Promise<WebSocketHandle> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    const messages: any[] = [];

    const messageHandler = (data: WebSocket.RawData) => {
      try {
        messages.push(JSON.parse(data.toString()));
      } catch {
        messages.push(data.toString());
      }
    };

    const errorHandler = (err: Error) => {
      cleanup();
      reject(err);
    };

    const openHandler = () => {
      cleanup();
      resolve({ socket, messages });
    };

    const closeHandler = () => {
      cleanup();
      reject(new Error('WebSocket closed before connection established'));
    };

    const cleanup = () => {
      socket.off('message', messageHandler);
      socket.off('error', errorHandler);
      socket.off('open', openHandler);
      socket.off('close', closeHandler);
    };

    socket.on('message', messageHandler);
    socket.on('error', errorHandler);
    socket.on('open', openHandler);
    socket.on('close', closeHandler);
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
