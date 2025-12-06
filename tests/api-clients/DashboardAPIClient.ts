import WebSocket from 'ws';
import { BaseAPIClient } from './BaseAPIClient';

export interface GPUInfo {
  name: string;
  total_mb: number;
  used_mb: number;
  free_mb: number;
  utilization: number;
}

export interface GPUProcess {
  pid: number;
  name: string;
  used_mb: number;
}

export interface VRAMStatusResponse {
  gpu: GPUInfo;
  processes: GPUProcess[];
}

export interface OllamaModel {
  id?: string;
  name: string;
  size?: string;
  size_mb?: number;
  loaded?: boolean;
}

export interface OllamaModelsResponse {
  count: number;
  models: OllamaModel[];
}

export type DashboardWebSocketCallback = (data: any) => void;

export class DashboardAPIClient extends BaseAPIClient {
  getVRAMStatus(): Promise<VRAMStatusResponse> {
    return this.get<VRAMStatusResponse>('/api/vram/status');
  }

  listOllamaModels(): Promise<OllamaModelsResponse> {
    return this.get<OllamaModelsResponse>('/api/models/ollama/list');
  }

  async getLoadedModels(): Promise<OllamaModel[]> {
    const response = await this.get<OllamaModelsResponse>('/api/models/ollama/loaded');
    return response.models;
  }

  loadModel(modelName: string): Promise<{ status: string }> {
    return this.post<{ status: string }>('/api/models/ollama/load', { model_name: modelName });
  }

  unloadModel(modelName: string): Promise<{ status: string }> {
    return this.post<{ status: string }>('/api/models/ollama/unload', { model_name: modelName });
  }

  downloadModel(modelName: string): Promise<{ status: string }> {
    return this.post<{ status: string }>('/api/models/ollama/download', { model_name: modelName });
  }

  connectVRAMWebSocket(callback: DashboardWebSocketCallback): Promise<WebSocket> {
    const url = this.baseUrl.replace(/^http/, 'ws') + '/ws/vram';
    return this.connectWebSocket(url, callback);
  }

  connectModelDownloadWebSocket(callback: DashboardWebSocketCallback): Promise<WebSocket> {
    const url = this.baseUrl.replace(/^http/, 'ws') + '/ws/model-downloads';
    return this.connectWebSocket(url, callback);
  }

  private connectWebSocket(url: string, callback: DashboardWebSocketCallback): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);

      ws.on('open', () => resolve(ws));
      ws.on('message', (data: WebSocket.RawData) => {
        try {
          const parsed = JSON.parse(data.toString());
          callback(parsed);
        } catch {
          callback(data.toString());
        }
      });
      ws.on('error', (err: Error) => reject(err));
    });
  }
}
