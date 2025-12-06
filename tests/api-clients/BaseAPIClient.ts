import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';

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
}

export class BaseAPIClient {
  protected readonly client: AxiosInstance;
  protected readonly maxRetries: number;
  protected readonly baseUrl: string;

  constructor(baseUrl: string, options: BaseAPIClientOptions = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.maxRetries = options.maxRetries ?? 3;

    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: options.timeoutMs ?? 30_000,
      headers: options.headers ?? { 'Content-Type': 'application/json' }
    });
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
}

