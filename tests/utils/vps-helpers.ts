import * as dotenv from 'dotenv';
import * as path from 'path';

/**
 * Default embedding models that should never be unloaded.
 * These are used when PRESERVE_EMBEDDING_MODELS env var is not set.
 */
export const DEFAULT_PRESERVE_EMBEDDING_MODELS = [
  'nomic-embed-text',
  'mxbai-embed-large',
  'all-minilm'
];

/**
 * Default GPU-intensive services (consume significant VRAM).
 * These are used when GPU_INTENSIVE_SERVICES env var is not set.
 */
export const DEFAULT_GPU_INTENSIVE_SERVICES = [
  'comfyui',
  'stable_audio',
  'wan2gp',
  'yue',
  'diffrhythm',
  'audiocraft'
];

/**
 * Services that host embedding models (should not be stopped).
 */
export const EMBEDDING_HOST_SERVICES = [
  'ollama',
  'weaviate'
];

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

/**
 * Check if running in VPS environment
 */
export function isVPSEnvironment(): boolean {
  return process.env.TEST_ENVIRONMENT === 'vps';
}

/**
 * Check if running in CI environment
 */
export function isCIEnvironment(): boolean {
  return !!process.env.CI;
}

/**
 * Get the current test environment name
 */
export function getTestEnvironment(): 'vps' | 'ci' | 'local' {
  if (isVPSEnvironment()) return 'vps';
  if (isCIEnvironment()) return 'ci';
  return 'local';
}

export interface VPSConfig {
  baseUrl: string;
  dashboardApiUrl: string;
  gatewayApiUrl: string;
  testTimeout: number;
  headless: boolean;
  preserveEmbeddingModels: string[];
  gpuIntensiveServices: string[];
  serviceStartTimeout: number;
  serviceHealthInterval: number;
  maxServiceRetries: number;
  /**
   * Allow connections to servers with invalid/self-signed SSL certificates.
   * Set ALLOW_INSECURE_CONNECTIONS=true to enable.
   * @default false
   */
  allowInsecureConnections: boolean;
  auth?: {
    username: string;
    password: string;
  };
}

/**
 * Get VPS configuration from environment
 */
export function getVPSConfig(): VPSConfig {
  // Load VPS env file if available
  if (isVPSEnvironment()) {
    dotenv.config({ path: path.resolve(__dirname, '..', '.env.vps') });
  }
  dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

  const config: VPSConfig = {
    baseUrl: process.env.BASE_URL || 'http://localhost',
    dashboardApiUrl: process.env.DASHBOARD_API_URL || 'http://localhost',
    gatewayApiUrl: process.env.GATEWAY_API_URL || 'http://localhost:1301',
    testTimeout: parseEnvNumber(process.env.TEST_TIMEOUT, 60000),
    headless: process.env.HEADLESS !== 'false',
    preserveEmbeddingModels: parseEnvList(process.env.PRESERVE_EMBEDDING_MODELS, DEFAULT_PRESERVE_EMBEDDING_MODELS),
    gpuIntensiveServices: parseEnvList(process.env.GPU_INTENSIVE_SERVICES, DEFAULT_GPU_INTENSIVE_SERVICES),
    serviceStartTimeout: parseEnvNumber(process.env.SERVICE_START_TIMEOUT, 60000),
    serviceHealthInterval: parseEnvNumber(process.env.SERVICE_HEALTH_INTERVAL, 5000),
    maxServiceRetries: parseEnvNumber(process.env.MAX_SERVICE_RETRIES, 3),
    allowInsecureConnections: process.env.ALLOW_INSECURE_CONNECTIONS === 'true'
  };

  // Add auth if configured
  if (process.env.DASHBOARD_AUTH_USERNAME && process.env.DASHBOARD_AUTH_PASSWORD) {
    config.auth = {
      username: process.env.DASHBOARD_AUTH_USERNAME,
      password: process.env.DASHBOARD_AUTH_PASSWORD
    };
  }

  return config;
}

/**
 * Get service URL from environment
 */
export function getServiceUrl(serviceName: string): string | undefined {
  const envKey = `${serviceName.toUpperCase().replace(/-/g, '_')}_URL`;
  return process.env[envKey];
}

/**
 * Create an AbortSignal that times out after the specified milliseconds.
 * Uses AbortController + setTimeout for Node.js < 17.3 compatibility.
 */
function createTimeoutSignal(ms: number): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ms);
  return {
    signal: controller.signal,
    cleanup: () => clearTimeout(timeoutId)
  };
}

/**
 * Check if a response status indicates the service is ready.
 * Only accepts successful responses (2xx) and redirects (3xx).
 * Rejects 4xx client errors and 5xx server errors.
 */
function isServiceReady(status: number): boolean {
  // 2xx success codes
  if (status >= 200 && status < 300) {
    return true;
  }
  // 3xx redirect codes (service is responding, just redirecting)
  if (status >= 300 && status < 400) {
    return true;
  }
  // 4xx and 5xx are not considered "ready"
  return false;
}

/**
 * Wait for a VPS service to be reachable
 */
export async function waitForVPSService(
  url: string,
  timeoutMs: number = 30000
): Promise<boolean> {
  const start = Date.now();
  const pollInterval = 2000;
  const requestTimeout = 5000;

  while (Date.now() - start < timeoutMs) {
    const { signal, cleanup } = createTimeoutSignal(requestTimeout);
    try {
      const response = await fetch(url, {
        method: 'GET',
        signal
      });

      if (isServiceReady(response.status)) {
        return true;
      }
    } catch {
      // Service not ready yet (network error, timeout, etc.)
    } finally {
      cleanup();
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }

  return false;
}

/**
 * Log VPS environment info for debugging
 */
export function logVPSEnvironment(): void {
  const config = getVPSConfig();
  const env = getTestEnvironment();

  console.log('\n=== Test Environment ===');
  console.log(`Environment: ${env}`);
  console.log(`Base URL: ${config.baseUrl}`);
  console.log(`Dashboard API: ${config.dashboardApiUrl}`);
  console.log(`Gateway API: ${config.gatewayApiUrl}`);
  console.log(`Timeout: ${config.testTimeout}ms`);
  console.log(`Headless: ${config.headless}`);
  console.log(`Preserve Embeddings: ${config.preserveEmbeddingModels.join(', ')}`);
  console.log(`GPU Services: ${config.gpuIntensiveServices.join(', ')}`);
  if (config.auth) {
    console.log(`Auth: ${config.auth.username} (configured)`);
  }
  console.log('========================\n');
}

/**
 * Service IDs for common test scenarios
 */
export const ServiceIds = {
  DASHBOARD: 'dashboard',
  GATEWAY: 'gateway',
  OLLAMA: 'ollama',
  WEAVIATE: 'weaviate',
  COMFYUI: 'comfyui',
  ALLTALK: 'alltalk',
  WAN2GP: 'wan2gp',
  YUE: 'yue',
  DIFFRHYTHM: 'diffrhythm',
  MUSICGEN: 'musicgen',
  STABLE_AUDIO: 'stable_audio',
  N8N: 'n8n',
  OPEN_WEBUI: 'open_webui'
} as const;

export type ServiceId = typeof ServiceIds[keyof typeof ServiceIds];

/**
 * Get services required for a specific test suite
 */
export function getServicesForSuite(suite: string): ServiceId[] {
  const suiteServices: Record<string, ServiceId[]> = {
    'smoke': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.OLLAMA],
    'api': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.OLLAMA],
    'ui': [ServiceIds.DASHBOARD],
    'image': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.COMFYUI],
    'audio': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.ALLTALK],
    'music': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.YUE, ServiceIds.DIFFRHYTHM],
    'video': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.WAN2GP],
    'llm': [ServiceIds.DASHBOARD, ServiceIds.GATEWAY, ServiceIds.OLLAMA]
  };

  return suiteServices[suite] || [ServiceIds.DASHBOARD, ServiceIds.GATEWAY];
}
