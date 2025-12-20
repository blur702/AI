import WebSocket from "ws";
import { BaseAPIClient, BaseAPIClientOptions } from "./BaseAPIClient";

export interface UnifiedError {
  code: string;
  message: string;
  details?: unknown;
}

export interface UnifiedResponse<T = any> {
  success: boolean;
  data?: T;
  error?: UnifiedError;
  job_id?: string;
  timestamp?: string;
}

export interface APIKeyInfo {
  name: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

export interface CreateAPIKeyResponse {
  key: string;
  name: string;
  created_at: string;
}

export interface JobInfo<TMeta = any> {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  createdAt: string;
  updatedAt: string;
  result?: unknown;
  error?: UnifiedError;
  meta?: TMeta;
}

export type GatewayWebSocketCallback = (data: any) => void;

export class GatewayAPIClient extends BaseAPIClient {
  getHealth(): Promise<UnifiedResponse> {
    return this.get<UnifiedResponse>("/health");
  }

  /**
   * Alias for getHealth for consistency with other clients
   */
  healthCheck(): Promise<UnifiedResponse> {
    return this.getHealth();
  }

  generateImage(request: any): Promise<UnifiedResponse> {
    return this.post<UnifiedResponse>("/generate/image", request);
  }

  generateVideo(request: any): Promise<UnifiedResponse> {
    return this.post<UnifiedResponse>("/generate/video", request);
  }

  generateAudio(request: any): Promise<UnifiedResponse> {
    return this.post<UnifiedResponse>("/generate/audio", request);
  }

  generateMusic(request: any): Promise<UnifiedResponse> {
    return this.post<UnifiedResponse>("/generate/music", request);
  }

  generateLLM(request: any): Promise<UnifiedResponse> {
    return this.post<UnifiedResponse>("/llm/generate", request);
  }

  listModels(): Promise<UnifiedResponse> {
    return this.get<UnifiedResponse>("/llm/models");
  }

  getJob(jobId: string): Promise<UnifiedResponse<JobInfo>> {
    return this.get<UnifiedResponse<JobInfo>>(`/jobs/${jobId}`);
  }

  listJobs(skip = 0, limit = 20): Promise<UnifiedResponse<JobInfo[]>> {
    return this.get<UnifiedResponse<JobInfo[]>>("/jobs", { skip, limit });
  }

  cancelJob(jobId: string): Promise<UnifiedResponse> {
    return this.post<UnifiedResponse>(`/jobs/${jobId}/cancel`);
  }

  connectJobWebSocket(
    jobId: string,
    callback: GatewayWebSocketCallback,
  ): Promise<WebSocket> {
    const url = this.baseUrl.replace(/^http/, "ws") + `/ws/jobs/${jobId}`;
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);

      ws.on("open", () => resolve(ws));
      ws.on("message", (data) => {
        try {
          const parsed = JSON.parse(data.toString());
          callback(parsed);
        } catch {
          callback(data.toString());
        }
      });
      ws.on("error", (err) => reject(err));
    });
  }

  async waitForJobCompletion(
    jobId: string,
    timeoutMs = 600_000,
  ): Promise<JobInfo> {
    const start = Date.now();

    while (Date.now() - start < timeoutMs) {
      const response = await this.getJob(jobId);
      if (!response.success || !response.data) {
        throw new Error(
          `Unexpected job response while waiting: ${JSON.stringify(response)}`,
        );
      }

      const job = response.data;
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        return job;
      }

      await new Promise((resolve) => setTimeout(resolve, 2000));
    }

    throw new Error(`Job ${jobId} did not complete within ${timeoutMs}ms`);
  }

  // Authentication Methods

  /**
   * Creates a new API key with the given name.
   */
  createAPIKey(name: string): Promise<UnifiedResponse<CreateAPIKeyResponse>> {
    return this.post<UnifiedResponse<CreateAPIKeyResponse>>("/auth/keys", {
      name,
    });
  }

  /**
   * Lists all API keys (without exposing the actual key values).
   */
  listAPIKeys(): Promise<UnifiedResponse<{ keys: APIKeyInfo[] }>> {
    return this.get<UnifiedResponse<{ keys: APIKeyInfo[] }>>("/auth/keys");
  }

  /**
   * Deactivates an API key.
   */
  deactivateAPIKey(
    key: string,
  ): Promise<UnifiedResponse<{ success: boolean }>> {
    return this.delete<UnifiedResponse<{ success: boolean }>>(
      `/auth/keys/${key}`,
    );
  }

  /**
   * Override withHeaders to return a GatewayAPIClient instance.
   * Uses stored configuration from the base class instead of reading Axios internals.
   */
  override withHeaders(headers: Record<string, string>): GatewayAPIClient {
    const options = this.getOptions();
    return new GatewayAPIClient(this.baseUrl, {
      ...options,
      headers: { ...options.headers, ...headers },
    });
  }

  /**
   * Returns a new GatewayAPIClient instance with the X-API-Key header set.
   * Delegates to withHeaders to reuse the safe header-augmentation mechanism.
   */
  withAPIKey(apiKey: string): GatewayAPIClient {
    return this.withHeaders({ "X-API-Key": apiKey });
  }
}
