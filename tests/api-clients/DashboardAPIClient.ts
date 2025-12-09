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

export interface ServiceInfo {
  id: string;
  name: string;
  status: 'running' | 'stopped' | 'starting' | 'stopping' | 'error' | 'unknown';
  port?: number;
  url?: string;
  gpu_intensive?: boolean;
  last_checked?: string;
  error?: string;
}

export interface ServicesResponse {
  services: Record<string, ServiceInfo>;
}

export interface ServiceActionResponse {
  success: boolean;
  message?: string;
  error?: string;
}

export type DashboardWebSocketCallback = (data: any) => void;

export class DashboardAPIClient extends BaseAPIClient {
  // Service Management Methods

  /**
   * Get all services and their statuses
   */
  getServices(): Promise<ServicesResponse> {
    return this.get<ServicesResponse>('/api/services');
  }

  /**
   * Get status of a specific service
   */
  async getServiceStatus(serviceId: string): Promise<ServiceInfo> {
    const response = await this.getServices();
    const service = response.services[serviceId];
    if (!service) {
      throw new Error(`Service '${serviceId}' not found`);
    }
    return service;
  }

  /**
   * Start a service by ID
   */
  startService(serviceId: string): Promise<ServiceActionResponse> {
    return this.post<ServiceActionResponse>(`/api/services/${serviceId}/start`);
  }

  /**
   * Stop a service by ID
   */
  stopService(serviceId: string): Promise<ServiceActionResponse> {
    return this.post<ServiceActionResponse>(`/api/services/${serviceId}/stop`);
  }

  /**
   * Restart a service by ID
   */
  async restartService(serviceId: string): Promise<ServiceActionResponse> {
    await this.stopService(serviceId);
    await this.waitForServiceStatus(serviceId, 'stopped', 30000);
    return this.startService(serviceId);
  }

  /**
   * Wait for a service to reach a specific status
   * @param serviceId - The service ID to wait for
   * @param expectedStatus - The status to wait for
   * @param timeoutMs - Maximum time to wait (default: 60000ms)
   * @param pollIntervalMs - Interval between status checks (default: 5000ms)
   * @param maxConsecutiveErrors - Maximum consecutive transient errors before failing (default: 3)
   */
  async waitForServiceStatus(
    serviceId: string,
    expectedStatus: ServiceInfo['status'],
    timeoutMs: number = 60000,
    pollIntervalMs: number = 5000,
    maxConsecutiveErrors: number = 3
  ): Promise<void> {
    const start = Date.now();
    let consecutiveErrors = 0;

    const getElapsedMs = () => Date.now() - start;
    const formatContext = () =>
      `[serviceId=${serviceId}, expectedStatus=${expectedStatus}, elapsed=${getElapsedMs()}ms]`;

    while (getElapsedMs() < timeoutMs) {
      try {
        const status = await this.getServiceStatus(serviceId);
        // Reset consecutive error counter on successful request
        consecutiveErrors = 0;

        if (status.status === expectedStatus) {
          return;
        }
        if (status.status === 'error') {
          throw new Error(
            `Service '${serviceId}' entered error state: ${status.error} ${formatContext()}`
          );
        }
      } catch (error: any) {
        const errorStatus = error.status;
        const errorMessage = error.message || 'Unknown error';

        // Fatal errors: service not found - re-throw immediately
        if (errorMessage.includes('not found')) {
          throw error;
        }

        // Fatal errors: authentication/authorization failures - re-throw immediately
        if (errorStatus === 401 || errorStatus === 403) {
          throw new Error(
            `Authentication/authorization failed (${errorStatus}): ${errorMessage} ${formatContext()}`
          );
        }

        // Fatal errors: other client errors (4xx) - re-throw immediately
        if (errorStatus >= 400 && errorStatus < 500) {
          throw new Error(
            `Client error (${errorStatus}): ${errorMessage} ${formatContext()}`
          );
        }

        // Transient errors: network issues, server errors (5xx), timeouts
        consecutiveErrors++;
        console.warn(
          `[DashboardAPIClient] Transient error while polling service status ` +
          `(attempt ${consecutiveErrors}/${maxConsecutiveErrors}): ${errorMessage} ${formatContext()}`
        );

        // Fail fast if too many consecutive transient errors
        if (consecutiveErrors >= maxConsecutiveErrors) {
          throw new Error(
            `Too many consecutive errors (${consecutiveErrors}) while waiting for service: ` +
            `${errorMessage} ${formatContext()}`
          );
        }
      }
      await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
    }

    throw new Error(
      `Service '${serviceId}' did not reach status '${expectedStatus}' within ${timeoutMs}ms ${formatContext()}`
    );
  }

  /**
   * Wait for a service to become healthy (running)
   * @param serviceId - The service ID to wait for
   * @param timeoutMs - Maximum time to wait (default: 60000ms)
   * @param pollIntervalMs - Interval between status checks (default: 5000ms)
   */
  waitForHealthy(serviceId: string, timeoutMs: number = 60000, pollIntervalMs: number = 5000): Promise<void> {
    return this.waitForServiceStatus(serviceId, 'running', timeoutMs, pollIntervalMs);
  }

  /**
   * Check if a service is currently running
   */
  async isServiceRunning(serviceId: string): Promise<boolean> {
    try {
      const status = await this.getServiceStatus(serviceId);
      return status.status === 'running';
    } catch {
      return false;
    }
  }

  // VRAM and Model Management

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
