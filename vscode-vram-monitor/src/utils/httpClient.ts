import axios, { AxiosError } from "axios";
import {
  OllamaTimeoutError,
  OllamaConnectionError,
  OllamaServiceError,
} from "./ollamaErrors";

export interface HttpRequestOptions {
  url: string;
  method: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  timeout?: number;
}

// Shared HTTP abstraction used by the Ollama service to keep retries/tests centralized.
export async function httpRequest<T>(options: HttpRequestOptions): Promise<T> {
  const timeoutMs = options.timeout ?? 30000;
  const config = {
    url: options.url,
    method: options.method,
    timeout: timeoutMs,
    headers: {
      Accept: "application/json",
      ...(options.headers ?? {}),
    },
    data: options.body,
  };

  try {
    const response = await axios.request<T>(config);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError;
      const code = axiosError.code;

      if (code === "ECONNABORTED") {
        throw new OllamaTimeoutError(timeoutMs, {
          url: options.url,
          cause: error,
        });
      }

      if (
        code === "ECONNREFUSED" ||
        code === "ENOTFOUND" ||
        code === "EAI_AGAIN"
      ) {
        throw new OllamaConnectionError("Failed to reach Ollama service", {
          url: options.url,
          code,
          cause: error,
        });
      }

      if (axiosError.response) {
        throw new OllamaServiceError(
          `Request failed with status ${axiosError.response.status}`,
          {
            url: options.url,
            statusCode: axiosError.response.status,
            responseBody: axiosError.response.data,
            cause: error,
          },
        );
      }
    }

    throw new OllamaServiceError("Unexpected HTTP error", {
      url: options.url,
      cause: error as Error,
    });
  }
}
