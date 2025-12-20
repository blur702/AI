import {
  VRAMData,
  GPUData,
  OllamaModel,
  GPUProcess,
  EMPTY_VRAM_DATA,
  isGPUData,
  isOllamaModel,
  isGPUProcess,
} from "../types/vramTypes";
import {
  PythonPaths,
  ExecutionOptions,
  fetchVRAMDataRaw,
  PythonNotFoundError,
  VRAMManagerNotFoundError,
  ExecutionTimeoutError,
  PythonBridgeError,
} from "./pythonBridge";

export type FetchErrorType =
  | "python_not_found"
  | "vram_manager_not_found"
  | "timeout"
  | "parse_error"
  | "execution_error";

export interface FetchResult {
  data: VRAMData;
  success: boolean;
  error?: string;
  errorType?: FetchErrorType;
}

/**
 * Safely parses GPU data from raw JSON object
 */
function parseGPUData(raw: unknown): GPUData | null {
  if (raw === null || raw === undefined) {
    return null;
  }
  if (!isGPUData(raw)) {
    return null;
  }

  const gpuRaw = raw as unknown as Record<string, unknown>;

  // Build the GPUData object
  const gpuData: GPUData = {
    name: String(gpuRaw.name || "Unknown GPU"),
    total_mb: Number(gpuRaw.total_mb || 0),
    used_mb: Number(gpuRaw.used_mb || 0),
    free_mb: Number(gpuRaw.free_mb || 0),
    utilization: Number(gpuRaw.utilization || 0),
    gpus: [],
    aggregate: {
      total_mb: Number(gpuRaw.total_mb || 0),
      used_mb: Number(gpuRaw.used_mb || 0),
      free_mb: Number(gpuRaw.free_mb || 0),
      utilization: Number(gpuRaw.utilization || 0),
    },
  };

  // Parse gpus array if present
  if (Array.isArray(gpuRaw.gpus)) {
    gpuData.gpus = gpuRaw.gpus.map((gpu: unknown, index: number) => {
      const g = gpu as Record<string, unknown>;
      return {
        index: Number(g.index ?? index),
        id: String(g.id || ""),
        name: String(g.name || "Unknown"),
        total_mb: Number(g.total_mb || 0),
        used_mb: Number(g.used_mb || 0),
        free_mb: Number(g.free_mb || 0),
        utilization: Number(g.utilization || 0),
      };
    });
  }

  // Parse aggregate if present
  if (typeof gpuRaw.aggregate === "object" && gpuRaw.aggregate !== null) {
    const agg = gpuRaw.aggregate as Record<string, unknown>;
    gpuData.aggregate = {
      total_mb: Number(agg.total_mb || gpuData.total_mb),
      used_mb: Number(agg.used_mb || gpuData.used_mb),
      free_mb: Number(agg.free_mb || gpuData.free_mb),
      utilization: Number(agg.utilization || gpuData.utilization),
    };
  }

  return gpuData;
}

/**
 * Safely parses loaded models array from raw JSON.
 * Uses relaxed type guard that only requires 'name' - other fields are defaulted.
 */
function parseLoadedModels(raw: unknown): OllamaModel[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw.filter(isOllamaModel).map((item) => {
    const model = item as Record<string, unknown>;
    return {
      name: String(model.name),
      id: String(model.id ?? ""),
      size: String(model.size ?? ""),
      processor: String(model.processor ?? ""),
    };
  });
}

/**
 * Safely parses GPU processes array from raw JSON.
 * Uses relaxed type guard that only requires 'pid' and 'name' - memory is defaulted.
 */
function parseGPUProcesses(raw: unknown): GPUProcess[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw.filter(isGPUProcess).map((item) => {
    const proc = item as Record<string, unknown>;
    return {
      pid: String(proc.pid),
      name: String(proc.name),
      memory: String(proc.memory ?? ""),
    };
  });
}

/**
 * Parses raw JSON string into VRAMData structure
 */
function parseVRAMData(jsonString: string): VRAMData {
  const raw = JSON.parse(jsonString);
  if (typeof raw !== "object" || raw === null) {
    throw new Error("Invalid JSON structure: expected object");
  }

  const data = raw as Record<string, unknown>;
  return {
    gpu: parseGPUData(data.gpu),
    loaded_models: parseLoadedModels(data.loaded_models),
    gpu_processes: parseGPUProcesses(data.gpu_processes),
  };
}

/**
 * Fetches VRAM data from vram_manager.py
 * Returns a FetchResult with data and error information
 */
export async function fetchVRAMData(
  paths: PythonPaths,
  options?: ExecutionOptions,
): Promise<FetchResult> {
  try {
    const rawJson = await fetchVRAMDataRaw(paths, options);
    const data = parseVRAMData(rawJson);
    return {
      data,
      success: true,
    };
  } catch (error) {
    if (error instanceof PythonNotFoundError) {
      return {
        data: EMPTY_VRAM_DATA,
        success: false,
        error: error.message,
        errorType: "python_not_found",
      };
    }

    if (error instanceof VRAMManagerNotFoundError) {
      return {
        data: EMPTY_VRAM_DATA,
        success: false,
        error: error.message,
        errorType: "vram_manager_not_found",
      };
    }

    if (error instanceof ExecutionTimeoutError) {
      return {
        data: EMPTY_VRAM_DATA,
        success: false,
        error: error.message,
        errorType: "timeout",
      };
    }

    if (error instanceof SyntaxError) {
      return {
        data: EMPTY_VRAM_DATA,
        success: false,
        error: `JSON parse error: ${error.message}`,
        errorType: "parse_error",
      };
    }

    if (error instanceof PythonBridgeError) {
      return {
        data: EMPTY_VRAM_DATA,
        success: false,
        error:
          error.message + (error.stderr ? `\nstderr: ${error.stderr}` : ""),
        errorType: "execution_error",
      };
    }

    // Unknown error
    const errorMessage = error instanceof Error ? error.message : String(error);
    return {
      data: EMPTY_VRAM_DATA,
      success: false,
      error: `Unknown error: ${errorMessage}`,
      errorType: "execution_error",
    };
  }
}
