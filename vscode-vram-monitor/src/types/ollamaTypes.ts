/**
 * Ollama model details
 */
export interface OllamaModelDetails {
  format?: string;
  family?: string;
  families?: string[];
  parameter_size?: string;
  quantization_level?: string;
}

/**
 * Ollama model info from /api/tags
 */
export interface OllamaModelInfo {
  name: string;
  size: number;
  modified_at: string;
  digest: string;
  details?: OllamaModelDetails;
}

/**
 * Ollama loaded model from /api/ps
 */
export interface OllamaLoadedModel {
  name: string;
  model: string;
  size: number;
  size_vram: number;
  expires_at: string;
}

/**
 * Response from /api/tags
 */
export interface OllamaTagsResponse {
  models: OllamaModelInfo[];
}

/**
 * Response from /api/ps
 */
export interface OllamaPsResponse {
  models: OllamaLoadedModel[];
}

function isObject(obj: unknown): obj is Record<string, unknown> {
  return typeof obj === "object" && obj !== null;
}

export function isOllamaModelInfo(obj: unknown): obj is OllamaModelInfo {
  if (!isObject(obj)) {
    return false;
  }
  return (
    typeof obj.name === "string" &&
    typeof obj.size === "number" &&
    typeof obj.modified_at === "string" &&
    typeof obj.digest === "string" &&
    (obj.details === undefined || isObject(obj.details))
  );
}

export function isOllamaLoadedModel(obj: unknown): obj is OllamaLoadedModel {
  if (!isObject(obj)) {
    return false;
  }
  return (
    typeof obj.name === "string" &&
    typeof obj.model === "string" &&
    typeof obj.size === "number" &&
    typeof obj.size_vram === "number" &&
    typeof obj.expires_at === "string"
  );
}

export function isOllamaTagsResponse(obj: unknown): obj is OllamaTagsResponse {
  if (!isObject(obj)) {
    return false;
  }
  return (
    Array.isArray(obj.models) &&
    obj.models.every((model: unknown) => isOllamaModelInfo(model))
  );
}

export function isOllamaPsResponse(obj: unknown): obj is OllamaPsResponse {
  if (!isObject(obj)) {
    return false;
  }
  return (
    Array.isArray(obj.models) &&
    obj.models.every((model: unknown) => isOllamaLoadedModel(model))
  );
}
