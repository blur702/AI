import { useState, useEffect, useCallback, useRef } from 'react';
import { getApiBase } from '../config/services';
import type {
  OllamaModelDetailed,
  ModelsDetailedResponse,
  ModelActionResponse,
  ModelDownloadProgress,
  ModelLoadProgress,
  GpuInfo,
} from '../types';

interface UseModelsOptions {
  pollingInterval?: number;
  autoFetch?: boolean;
}

interface UseModelsReturn {
  models: OllamaModelDetailed[];
  loadedModels: OllamaModelDetailed[];
  availableModels: OllamaModelDetailed[];
  downloadingModels: Record<string, ModelDownloadProgress>;
  loadingModels: Record<string, ModelLoadProgress>;
  gpuInfo: GpuInfo | null;
  loading: boolean;
  error: string | null;
  totalCount: number;
  loadedCount: number;
  refresh: () => Promise<void>;
  loadModel: (modelName: string, expectedVramMb?: number) => Promise<ModelActionResponse>;
  unloadModel: (modelName: string, expectedVramMb?: number) => Promise<ModelActionResponse>;
  downloadModel: (modelName: string) => Promise<ModelActionResponse>;
  removeModel: (modelName: string) => Promise<ModelActionResponse>;
  getModelInfo: (modelName: string) => Promise<OllamaModelDetailed | null>;
}

export function useModels(options: UseModelsOptions = {}): UseModelsReturn {
  const { pollingInterval = 10000, autoFetch = true } = options;

  const [models, setModels] = useState<OllamaModelDetailed[]>([]);
  const [downloadingModels, setDownloadingModels] = useState<Record<string, ModelDownloadProgress>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, ModelLoadProgress>>({});
  const [gpuInfo, setGpuInfo] = useState<GpuInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const getAuthHeaders = useCallback(() => {
    const username = localStorage.getItem('auth_username') || '';
    const password = localStorage.getItem('auth_password') || '';
    return {
      'Authorization': `Basic ${btoa(`${username}:${password}`)}`,
      'Content-Type': 'application/json',
    };
  }, []);

  const fetchModels = useCallback(async () => {
    if (!mountedRef.current) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/detailed`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch models: ${response.statusText}`);
      }

      const data: ModelsDetailedResponse = await response.json();

      if (mountedRef.current) {
        setModels(data.models);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch models');
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [getAuthHeaders]);

  const fetchGpuInfo = useCallback(async () => {
    if (!mountedRef.current) return;

    try {
      const response = await fetch(`${getApiBase()}/api/vram/status`, {
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        if (mountedRef.current && data.gpu) {
          setGpuInfo(data.gpu);
        }
      }
    } catch (err) {
      // GPU info is not critical, but log for debugging
      console.debug('Failed to fetch GPU info:', err);
    }
  }, [getAuthHeaders]);

  const refresh = useCallback(async () => {
    await Promise.all([fetchModels(), fetchGpuInfo()]);
  }, [fetchModels, fetchGpuInfo]);

  const loadModel = useCallback(async (modelName: string, expectedVramMb?: number): Promise<ModelActionResponse> => {
    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/load`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ model_name: modelName, expected_vram_mb: expectedVramMb }),
      });

      const data: ModelActionResponse = await response.json();

      if (data.success) {
        // Add to loading models - progress will be updated via WebSocket
        setLoadingModels(prev => ({
          ...prev,
          [modelName]: {
            model_name: modelName,
            progress: 0,
            status: 'loading',
            action: 'load',
          },
        }));
      }

      return data;
    } catch (err) {
      return {
        success: false,
        message: err instanceof Error ? err.message : 'Failed to load model',
        model_name: modelName,
      };
    }
  }, [getAuthHeaders]);

  const unloadModel = useCallback(async (modelName: string, expectedVramMb?: number): Promise<ModelActionResponse> => {
    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/unload`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ model_name: modelName, expected_vram_mb: expectedVramMb }),
      });

      const data: ModelActionResponse = await response.json();

      if (data.success) {
        // Add to loading models - progress will be updated via WebSocket
        setLoadingModels(prev => ({
          ...prev,
          [modelName]: {
            model_name: modelName,
            progress: 0,
            status: 'unloading',
            action: 'unload',
          },
        }));
      }

      return data;
    } catch (err) {
      return {
        success: false,
        message: err instanceof Error ? err.message : 'Failed to unload model',
        model_name: modelName,
      };
    }
  }, [getAuthHeaders]);

  const downloadModel = useCallback(async (modelName: string): Promise<ModelActionResponse> => {
    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/download`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ model_name: modelName }),
      });

      const data: ModelActionResponse = await response.json();

      if (data.success) {
        // Add to downloading models
        setDownloadingModels(prev => ({
          ...prev,
          [modelName]: {
            model_name: modelName,
            progress: 'starting',
            status: 'downloading',
          },
        }));
      }

      return data;
    } catch (err) {
      return {
        success: false,
        message: err instanceof Error ? err.message : 'Failed to start download',
        model_name: modelName,
      };
    }
  }, [getAuthHeaders]);

  const removeModel = useCallback(async (modelName: string): Promise<ModelActionResponse> => {
    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/remove`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ model_name: modelName, confirm: true }),
      });

      const data: ModelActionResponse = await response.json();

      if (data.success) {
        await refresh();
      }

      return data;
    } catch (err) {
      return {
        success: false,
        message: err instanceof Error ? err.message : 'Failed to remove model',
        model_name: modelName,
      };
    }
  }, [getAuthHeaders, refresh]);

  const getModelInfo = useCallback(async (modelName: string): Promise<OllamaModelDetailed | null> => {
    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/info/${encodeURIComponent(modelName)}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        return null;
      }

      return await response.json();
    } catch {
      return null;
    }
  }, [getAuthHeaders]);

  // Update downloading models from WebSocket events
  const updateDownloadProgress = useCallback((progress: ModelDownloadProgress) => {
    setDownloadingModels(prev => {
      if (progress.status === 'complete' || progress.status === 'error') {
        // Remove from downloading and refresh models
        const { [progress.model_name]: _, ...rest } = prev;
        // Trigger refresh after download completes (with unmount guard)
        if (progress.status === 'complete') {
          setTimeout(() => {
            if (mountedRef.current) {
              refresh();
            }
          }, 1000);
        }
        return rest;
      }
      return {
        ...prev,
        [progress.model_name]: progress,
      };
    });
  }, [refresh]);

  // Update loading/unloading models from WebSocket events
  const updateLoadProgress = useCallback((progress: ModelLoadProgress) => {
    setLoadingModels(prev => {
      if (progress.status === 'complete' || progress.status === 'error') {
        // Remove from loading and refresh models
        const { [progress.model_name]: _, ...rest } = prev;
        // Trigger refresh after load/unload completes (with unmount guard)
        if (progress.status === 'complete') {
          setTimeout(() => {
            if (mountedRef.current) {
              refresh();
            }
          }, 500);
        }
        return rest;
      }
      return {
        ...prev,
        [progress.model_name]: progress,
      };
    });
  }, [refresh]);

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true;

    if (autoFetch) {
      refresh();
    }

    return () => {
      mountedRef.current = false;
    };
  }, [autoFetch, refresh]);

  // Polling
  useEffect(() => {
    if (!autoFetch || pollingInterval <= 0) return;

    const interval = setInterval(() => {
      if (mountedRef.current) {
        refresh();
      }
    }, pollingInterval);

    return () => clearInterval(interval);
  }, [autoFetch, pollingInterval, refresh]);

  // Expose download progress updater for WebSocket integration
  useEffect(() => {
    // Store the updater function on window for WebSocket access
    (window as unknown as { __updateModelDownloadProgress?: (p: ModelDownloadProgress) => void }).__updateModelDownloadProgress = updateDownloadProgress;

    return () => {
      delete (window as unknown as { __updateModelDownloadProgress?: (p: ModelDownloadProgress) => void }).__updateModelDownloadProgress;
    };
  }, [updateDownloadProgress]);

  // Expose load progress updater for WebSocket integration
  useEffect(() => {
    // Store the updater function on window for WebSocket access
    (window as unknown as { __updateModelLoadProgress?: (p: ModelLoadProgress) => void }).__updateModelLoadProgress = updateLoadProgress;

    return () => {
      delete (window as unknown as { __updateModelLoadProgress?: (p: ModelLoadProgress) => void }).__updateModelLoadProgress;
    };
  }, [updateLoadProgress]);

  const loadedModels = models.filter(m => m.is_loaded);
  const availableModels = models.filter(m => !m.is_loaded);

  return {
    models,
    loadedModels,
    availableModels,
    downloadingModels,
    loadingModels,
    gpuInfo,
    loading,
    error,
    totalCount: models.length,
    loadedCount: loadedModels.length,
    refresh,
    loadModel,
    unloadModel,
    downloadModel,
    removeModel,
    getModelInfo,
  };
}
