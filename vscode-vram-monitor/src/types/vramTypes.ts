/**
 * Information about a single GPU
 */
export interface GPUInfo {
    index: number;
    id?: string;
    name: string;
    total_mb: number;
    used_mb: number;
    free_mb: number;
    utilization?: number;
}

/**
 * Aggregate GPU data
 */
export interface GPUAggregate {
    total_mb: number;
    used_mb: number;
    free_mb: number;
    utilization: number;
}

/**
 * GPU data structure from vram_manager.py
 */
export interface GPUData {
    name: string;
    total_mb: number;
    used_mb: number;
    free_mb: number;
    utilization?: number;
    gpus?: GPUInfo[];
    aggregate?: GPUAggregate;
}

/**
 * Ollama model information
 */
export interface OllamaModel {
    name: string;
    id?: string;
    size?: string;
    processor?: string;
}

/**
 * GPU process information
 */
export interface GPUProcess {
    pid: string;
    name: string;
    memory?: string;
}

/**
 * Complete VRAM data structure
 */
export interface VRAMData {
    gpu: GPUData | null;
    loaded_models: OllamaModel[];
    gpu_processes: GPUProcess[];
}

/**
 * Default empty VRAM data structure for error cases
 */
export const EMPTY_VRAM_DATA: VRAMData = {
    gpu: null,
    loaded_models: [],
    gpu_processes: []
};

/**
 * Type guard to check if an object is a valid GPUInfo
 */
export function isGPUInfo(obj: unknown): obj is GPUInfo {
    if (typeof obj !== 'object' || obj === null) {
        return false;
    }
    const gpu = obj as Record<string, unknown>;
    return (
        typeof gpu.index === 'number' &&
        typeof gpu.name === 'string' &&
        typeof gpu.total_mb === 'number' &&
        typeof gpu.used_mb === 'number' &&
        typeof gpu.free_mb === 'number'
    );
}

/**
 * Type guard to check if an object is a valid GPUData
 */
export function isGPUData(obj: unknown): obj is GPUData {
    if (typeof obj !== 'object' || obj === null) {
        return false;
    }
    const gpu = obj as Record<string, unknown>;
    return (
        typeof gpu.name === 'string' &&
        typeof gpu.total_mb === 'number' &&
        typeof gpu.used_mb === 'number' &&
        typeof gpu.free_mb === 'number'
    );
}

/**
 * Type guard to check if an object has minimal required OllamaModel fields.
 * Only requires 'name' - other fields are optional and will be defaulted during parsing.
 */
export function isOllamaModel(obj: unknown): obj is { name: string } {
    if (typeof obj !== 'object' || obj === null) {
        return false;
    }
    const model = obj as Record<string, unknown>;
    // Only require 'name' - the minimal field needed to identify a model
    return typeof model.name === 'string';
}

/**
 * Type guard to check if an object has minimal required GPUProcess fields.
 * Only requires 'pid' and 'name' - memory is optional and will be defaulted during parsing.
 */
export function isGPUProcess(obj: unknown): obj is { pid: string | number; name: string } {
    if (typeof obj !== 'object' || obj === null) {
        return false;
    }
    const proc = obj as Record<string, unknown>;
    // Only require 'pid' and 'name' - the minimal fields needed to identify a process
    // Accept pid as string or number (will be converted during parsing)
    return (
        (typeof proc.pid === 'string' || typeof proc.pid === 'number') &&
        typeof proc.name === 'string'
    );
}

/**
 * Type guard to check if an object is a valid VRAMData structure
 */
export function isVRAMData(obj: unknown): obj is VRAMData {
    if (typeof obj !== 'object' || obj === null) {
        return false;
    }
    const data = obj as Record<string, unknown>;
    // gpu can be null or a valid GPUData object
    if (data.gpu !== null && !isGPUData(data.gpu)) {
        return false;
    }
    // loaded_models must be an array
    if (!Array.isArray(data.loaded_models)) {
        return false;
    }
    // gpu_processes must be an array
    if (!Array.isArray(data.gpu_processes)) {
        return false;
    }
    return true;
}
