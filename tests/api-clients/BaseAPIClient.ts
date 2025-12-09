import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import https from 'https';

export class APIError extends Error {
  status?: number;
  data?: unknown;

  constructor(message: string, status?: number, data?: unknown) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.data = data;
  }
}

export class TimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TimeoutError';
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}

export interface BaseAPIClientOptions {
  timeoutMs?: number;
  headers?: Record<string, string>;
  maxRetries?: number;
  /**
   * Allow connections to servers with invalid/self-signed SSL certificates.
   * WARNING: This disables SSL certificate validation and should only be used
   * in test environments with self-signed certificates.
   * @default false
   */
  allowInsecureConnections?: boolean;
}

export class BaseAPIClient {
  protected readonly client: AxiosInstance;
  protected readonly maxRetries: number;
  protected readonly baseUrl: string;
  protected readonly timeoutMs: number;
  protected readonly headers: Record<string, string>;
  protected readonly allowInsecureConnections: boolean;

  constructor(baseUrl: string, options: BaseAPIClientOptions = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.maxRetries = options.maxRetries ?? 3;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.headers = options.headers ?? { 'Content-Type': 'application/json' };
    this.allowInsecureConnections = options.allowInsecureConnections ?? false;

    // Configure HTTPS agent based on security settings
    // Only disable certificate validation when explicitly opted in
    const httpsAgent = new https.Agent({
      rejectUnauthorized: !this.allowInsecureConnections
    });

    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: this.timeoutMs,
      headers: this.headers,
      httpsAgent
    });
  }

  /**
   * Returns the stored options for creating new client instances.
   * Subclasses can use this to preserve configuration when cloning.
   */
  protected getOptions(): BaseAPIClientOptions {
    return {
      timeoutMs: this.timeoutMs,
      maxRetries: this.maxRetries,
      headers: { ...this.headers },
      allowInsecureConnections: this.allowInsecureConnections
    };
  }

  protected async requestWithRetry<T>(config: AxiosRequestConfig, attempt = 1): Promise<T> {
    try {
      console.log('[BaseAPIClient] Request:', {
        method: config.method,
        url: config.url,
        params: config.params,
        data: config.data
      });
      const response: AxiosResponse<T> = await this.client.request<T>(config);
      console.log('[BaseAPIClient] Response:', {
        status: response.status,
        url: response.config.url
      });

      return response.data;
    } catch (error: any) {
      const status = error?.response?.status;
      const data = error?.response?.data;

      console.error('[BaseAPIClient] Error:', { status, data, message: error?.message, code: error?.code, url: this.baseUrl + config.url });

      // Don't retry 4xx client errors
      if (status >= 400 && status < 500) {
        throw new APIError('Client error - not retrying', status, data);
      }

      if (attempt >= this.maxRetries) {
        if (error.code === 'ECONNABORTED') {
          throw new TimeoutError(`Request timed out after ${attempt} attempts`);
        }
        if (!error.response) {
          throw new NetworkError(error.message || 'Network error');
        }
        throw new APIError('API request failed', status, data);
      }

      const delay = 2 ** attempt * 250;
      await new Promise((resolve) => setTimeout(resolve, delay));
      return this.requestWithRetry<T>(config, attempt + 1);
    }
  }

  get<T = any>(endpoint: string, params?: Record<string, any>): Promise<T> {
    return this.requestWithRetry<T>({ method: 'GET', url: endpoint, params });
  }

  post<T = any>(endpoint: string, body?: any): Promise<T> {
    return this.requestWithRetry<T>({ method: 'POST', url: endpoint, data: body });
  }

  put<T = any>(endpoint: string, body?: any): Promise<T> {
    return this.requestWithRetry<T>({ method: 'PUT', url: endpoint, data: body });
  }

  delete<T = any>(endpoint: string): Promise<T> {
    return this.requestWithRetry<T>({ method: 'DELETE', url: endpoint });
  }

  /**
   * Creates a new client instance with additional headers merged in.
   * Uses stored configuration instead of reading from Axios internals.
   * Subclasses should override this method to return the correct subclass type.
   */
  withHeaders(headers: Record<string, string>): BaseAPIClient {
    const options = this.getOptions();
    return new BaseAPIClient(this.baseUrl, {
      ...options,
      headers: { ...options.headers, ...headers }
    });
  }

  /**
   * Returns the base URL of this client.
   */
  getBaseUrl(): string {
    return this.baseUrl;
  }
}

