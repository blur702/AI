/**
 * Sample TypeScript module for testing the code parser.
 *
 * This module contains various TypeScript constructs to test the parser's
 * ability to extract interfaces, types, classes, functions, and variables.
 */

import { EventEmitter } from "events";

/**
 * Configuration options for services.
 */
export interface ServiceConfig {
  /** Service name identifier */
  name: string;
  /** Base URL for API calls */
  baseUrl: string;
  /** Request timeout in milliseconds */
  timeout?: number;
  /** Enable debug logging */
  debug?: boolean;
}

/**
 * Response structure from API calls.
 */
export interface ApiResponse<T = unknown> {
  /** Response data */
  data: T;
  /** HTTP status code */
  status: number;
  /** Response headers */
  headers: Record<string, string>;
}

/**
 * Service status type.
 */
export type ServiceStatus = "idle" | "running" | "stopped" | "error";

/**
 * Union type for identifiers.
 */
export type Identifier = string | number;

/**
 * Callback function type for event handlers.
 */
export type EventCallback<T = void> = (event: T) => void;

/** Default timeout value in milliseconds */
export const DEFAULT_TIMEOUT = 30000;

/** Maximum retry attempts */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const MAX_RETRIES = 3;

/**
 * Simple utility function to add numbers.
 *
 * @param a - First number
 * @param b - Second number
 * @returns Sum of a and b
 */
export function add(a: number, b: number): number {
  return a + b;
}

/**
 * Async function to fetch data from URL.
 *
 * @param url - The URL to fetch
 * @param options - Optional fetch options
 * @returns Promise resolving to API response
 */
export async function fetchData<T>(
  url: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  const response = await fetch(url, options);
  const data = await response.json();
  return {
    data: data as T,
    status: response.status,
    headers: Object.fromEntries(response.headers.entries()),
  };
}

/**
 * Arrow function assigned to variable.
 */
export const multiply = (a: number, b: number): number => a * b;

/**
 * Async arrow function.
 */
export const delay = async (ms: number): Promise<void> => {
  return new Promise((resolve) => setTimeout(resolve, ms));
};

/**
 * Abstract base class for services.
 */
export abstract class BaseService {
  /** Service name */
  protected readonly name: string;

  /** Service status */
  protected status: ServiceStatus = "idle";

  /**
   * Create a new service instance.
   *
   * @param name - Service name
   */
  constructor(name: string) {
    this.name = name;
  }

  /**
   * Get the service name.
   *
   * @returns Service name string
   */
  getName(): string {
    return this.name;
  }

  /**
   * Get the current status.
   *
   * @returns Current service status
   */
  getStatus(): ServiceStatus {
    return this.status;
  }

  /**
   * Abstract method to start the service.
   */
  abstract start(): Promise<void>;

  /**
   * Abstract method to stop the service.
   */
  abstract stop(): Promise<void>;
}

/**
 * Concrete service implementation with configuration.
 *
 * @example
 * ```typescript
 * const service = new ConfiguredService({
 *   name: "api",
 *   baseUrl: "https://api.example.com",
 *   timeout: 5000,
 * });
 * await service.start();
 * ```
 */
export class ConfiguredService extends BaseService {
  /** Service configuration */
  private config: ServiceConfig;

  /** Event emitter for service events */
  private emitter: EventEmitter;

  /**
   * Create a configured service.
   *
   * @param config - Service configuration options
   */
  constructor(config: ServiceConfig) {
    super(config.name);
    this.config = config;
    this.emitter = new EventEmitter();
  }

  /**
   * Get the service configuration.
   *
   * @returns Current configuration object
   */
  getConfig(): ServiceConfig {
    return { ...this.config };
  }

  /**
   * Update configuration options.
   *
   * @param updates - Partial configuration updates
   */
  updateConfig(updates: Partial<ServiceConfig>): void {
    this.config = { ...this.config, ...updates };
    this.emitter.emit("configChanged", this.config);
  }

  /**
   * Start the service.
   */
  async start(): Promise<void> {
    this.status = "running";
    this.emitter.emit("started");
  }

  /**
   * Stop the service.
   */
  async stop(): Promise<void> {
    this.status = "stopped";
    this.emitter.emit("stopped");
  }

  /**
   * Subscribe to service events.
   *
   * @param event - Event name
   * @param callback - Event handler callback
   */
  on<T>(event: string, callback: EventCallback<T>): void {
    this.emitter.on(event, callback);
  }

  /**
   * Static factory method to create service from config object.
   *
   * @param config - Configuration object
   * @returns New ConfiguredService instance
   */
  static fromConfig(config: ServiceConfig): ConfiguredService {
    return new ConfiguredService(config);
  }
}

/**
 * Enum for log levels.
 */
export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

/**
 * Simple logging utility class.
 */
export class Logger {
  private level: LogLevel;
  private prefix: string;

  constructor(prefix: string = "", level: LogLevel = LogLevel.INFO) {
    this.prefix = prefix;
    this.level = level;
  }

  /**
   * Log a debug message.
   */
  debug(message: string): void {
    if (this.level <= LogLevel.DEBUG) {
      console.debug(`${this.prefix}[DEBUG] ${message}`);
    }
  }

  /**
   * Log an info message.
   */
  info(message: string): void {
    if (this.level <= LogLevel.INFO) {
      console.info(`${this.prefix}[INFO] ${message}`);
    }
  }

  /**
   * Log a warning message.
   */
  warn(message: string): void {
    if (this.level <= LogLevel.WARN) {
      console.warn(`${this.prefix}[WARN] ${message}`);
    }
  }

  /**
   * Log an error message.
   */
  error(message: string): void {
    console.error(`${this.prefix}[ERROR] ${message}`);
  }
}
