import { DashboardAPIClient, ServiceInfo } from '../api-clients/DashboardAPIClient';
import {
  DEFAULT_PRESERVE_EMBEDDING_MODELS,
  DEFAULT_GPU_INTENSIVE_SERVICES,
  EMBEDDING_HOST_SERVICES
} from './vps-helpers';

export interface ServiceOrchestrationConfig {
  /** Timeout for starting a single service (ms) */
  startTimeout: number;
  /** Interval between health checks (ms) */
  healthInterval: number;
  /** Maximum retries for service start */
  maxRetries: number;
  /** Embedding models to preserve during VRAM cleanup */
  preserveEmbeddingModels: string[];
  /** GPU-intensive services that consume significant VRAM */
  gpuIntensiveServices: string[];
  /** Services that host embedding models (should not be stopped) */
  embeddingHostServices: string[];
}

/**
 * Parse a comma-separated environment variable into a clean array.
 * Trims whitespace and filters empty entries.
 */
function parseEnvList(value: string | undefined, defaultArray: string[]): string[] {
  if (!value) {
    return [...defaultArray];
  }
  return value.split(',').map(s => s.trim()).filter(s => s.length > 0);
}

/**
 * Parse a numeric environment variable with proper handling of 0 values.
 * Returns the default only when the env var is undefined or not a valid number.
 * Preserves 0 as a valid value (unlike `Number(env) || default` which treats 0 as falsy).
 */
function parseEnvNumber(value: string | undefined, defaultValue: number): number {
  if (value === undefined || value === '') {
    return defaultValue;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? defaultValue : parsed;
}

const DEFAULT_CONFIG: ServiceOrchestrationConfig = {
  startTimeout: parseEnvNumber(process.env.SERVICE_START_TIMEOUT, 60000),
  healthInterval: parseEnvNumber(process.env.SERVICE_HEALTH_INTERVAL, 5000),
  maxRetries: parseEnvNumber(process.env.MAX_SERVICE_RETRIES, 3),
  preserveEmbeddingModels: parseEnvList(
    process.env.PRESERVE_EMBEDDING_MODELS,
    DEFAULT_PRESERVE_EMBEDDING_MODELS
  ),
  gpuIntensiveServices: parseEnvList(
    process.env.GPU_INTENSIVE_SERVICES,
    DEFAULT_GPU_INTENSIVE_SERVICES
  ),
  embeddingHostServices: [...EMBEDDING_HOST_SERVICES]
};

export class ServiceOrchestrator {
  private client: DashboardAPIClient;
  private config: ServiceOrchestrationConfig;
  private startedServices: Set<string> = new Set();

  constructor(client: DashboardAPIClient, config: Partial<ServiceOrchestrationConfig> = {}) {
    this.client = client;
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Ensure a service is running. Start it if not already running.
   */
  async ensureServiceRunning(serviceId: string): Promise<void> {
    console.log(`[ServiceOrchestrator] Ensuring service '${serviceId}' is running...`);

    let attempts = 0;
    while (attempts < this.config.maxRetries) {
      try {
        const isRunning = await this.client.isServiceRunning(serviceId);

        if (isRunning) {
          console.log(`[ServiceOrchestrator] Service '${serviceId}' is already running`);
          return;
        }

        console.log(`[ServiceOrchestrator] Starting service '${serviceId}' (attempt ${attempts + 1}/${this.config.maxRetries})`);
        await this.client.startService(serviceId);
        await this.client.waitForHealthy(serviceId, this.config.startTimeout, this.config.healthInterval);

        this.startedServices.add(serviceId);
        console.log(`[ServiceOrchestrator] Service '${serviceId}' is now running`);
        return;
      } catch (error: any) {
        attempts++;
        console.error(`[ServiceOrchestrator] Failed to start '${serviceId}': ${error.message}`);

        if (attempts >= this.config.maxRetries) {
          throw new Error(`Failed to start service '${serviceId}' after ${this.config.maxRetries} attempts: ${error.message}`);
        }

        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, this.config.healthInterval));
      }
    }
  }

  /**
   * Start multiple services concurrently
   */
  async startServicesForSuite(serviceIds: string[]): Promise<void> {
    console.log(`[ServiceOrchestrator] Starting services for suite: ${serviceIds.join(', ')}`);

    const results = await Promise.allSettled(
      serviceIds.map(id => this.ensureServiceRunning(id))
    );

    const failures = results
      .map((result, index) => ({ result, serviceId: serviceIds[index] }))
      .filter(({ result }) => result.status === 'rejected');

    if (failures.length > 0) {
      const errorMessages = failures
        .map(({ serviceId, result }) => `${serviceId}: ${(result as PromiseRejectedResult).reason}`)
        .join('; ');
      throw new Error(`Failed to start services: ${errorMessages}`);
    }

    console.log(`[ServiceOrchestrator] All services started successfully`);
  }

  /**
   * Stop unused services to free VRAM.
   * Preserves embedding host services and specified keep-alive services.
   */
  async stopUnusedServices(keepRunning: string[] = []): Promise<void> {
    const keepSet = new Set([
      ...keepRunning,
      ...this.config.embeddingHostServices
    ]);

    console.log(`[ServiceOrchestrator] Stopping unused services (keeping: ${Array.from(keepSet).join(', ')})`);

    try {
      const { services } = await this.client.getServices();

      const servicesToStop = Object.entries(services)
        .filter(([id, info]) => {
          // Keep essential services
          if (keepSet.has(id)) return false;
          // Only stop GPU-intensive services that are running
          if (!this.config.gpuIntensiveServices.includes(id)) return false;
          return info.status === 'running';
        })
        .map(([id]) => id);

      if (servicesToStop.length === 0) {
        console.log(`[ServiceOrchestrator] No services to stop`);
        return;
      }

      console.log(`[ServiceOrchestrator] Stopping services: ${servicesToStop.join(', ')}`);

      await Promise.allSettled(
        servicesToStop.map(id => this.client.stopService(id))
      );

      console.log(`[ServiceOrchestrator] Cleanup complete`);
    } catch (error: any) {
      console.error(`[ServiceOrchestrator] Failed to stop unused services: ${error.message}`);
    }
  }

  /**
   * Manage VRAM by unloading non-essential models.
   * Preserves embedding models by default.
   */
  async manageVRAM(preserveEmbedding: boolean = true): Promise<void> {
    console.log(`[ServiceOrchestrator] Managing VRAM (preserveEmbedding: ${preserveEmbedding})`);

    try {
      const loadedModels = await this.client.getLoadedModels();

      if (loadedModels.length === 0) {
        console.log(`[ServiceOrchestrator] No models currently loaded`);
        return;
      }

      const modelsToUnload = loadedModels.filter(model => {
        const modelName = model.name.toLowerCase();

        // Preserve embedding models if requested
        if (preserveEmbedding) {
          const isEmbedding = this.config.preserveEmbeddingModels.some(
            embedModel => modelName.includes(embedModel.toLowerCase())
          );
          if (isEmbedding) {
            console.log(`[ServiceOrchestrator] Preserving embedding model: ${model.name}`);
            return false;
          }
        }

        return true;
      });

      if (modelsToUnload.length === 0) {
        console.log(`[ServiceOrchestrator] No models to unload`);
        return;
      }

      console.log(`[ServiceOrchestrator] Unloading models: ${modelsToUnload.map(m => m.name).join(', ')}`);

      for (const model of modelsToUnload) {
        try {
          await this.client.unloadModel(model.name);
          console.log(`[ServiceOrchestrator] Unloaded model: ${model.name}`);
        } catch (error: any) {
          console.error(`[ServiceOrchestrator] Failed to unload ${model.name}: ${error.message}`);
        }
      }
    } catch (error: any) {
      console.error(`[ServiceOrchestrator] Failed to manage VRAM: ${error.message}`);
    }
  }

  /**
   * Get list of services that were started by this orchestrator
   */
  getStartedServices(): string[] {
    return Array.from(this.startedServices);
  }

  /**
   * Cleanup: stop all services that were started by this orchestrator
   */
  async cleanup(): Promise<void> {
    const servicesToStop = Array.from(this.startedServices)
      .filter(id => !this.config.embeddingHostServices.includes(id));

    if (servicesToStop.length === 0) {
      console.log(`[ServiceOrchestrator] No services to cleanup`);
      return;
    }

    console.log(`[ServiceOrchestrator] Cleaning up started services: ${servicesToStop.join(', ')}`);

    await Promise.allSettled(
      servicesToStop.map(id => this.client.stopService(id))
    );

    this.startedServices.clear();
    console.log(`[ServiceOrchestrator] Cleanup complete`);
  }

  /**
   * Get current VRAM status
   */
  async getVRAMStatus(): Promise<any> {
    return this.client.getVRAMStatus();
  }

  /**
   * Get all service statuses
   */
  async getAllServices(): Promise<{ services: Record<string, ServiceInfo> }> {
    return this.client.getServices();
  }
}
