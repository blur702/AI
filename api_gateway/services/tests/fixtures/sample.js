/**
 * Sample JavaScript module for testing the code parser.
 *
 * This module contains various JavaScript constructs to test the parser's
 * ability to extract functions, classes, and variables from plain JS.
 */

const EventEmitter = require("events");

/**
 * Default timeout value in milliseconds.
 * @type {number}
 */
const DEFAULT_TIMEOUT = 30000;

/**
 * Maximum retry attempts.
 * @type {number}
 */
const MAX_RETRIES = 3;

/**
 * Service status values.
 */
var ServiceStatus = {
  IDLE: "idle",
  RUNNING: "running",
  STOPPED: "stopped",
  ERROR: "error",
};

/**
 * Simple utility function to add numbers.
 *
 * @param {number} a - First number
 * @param {number} b - Second number
 * @returns {number} Sum of a and b
 */
function add(a, b) {
  return a + b;
}

/**
 * Subtract two numbers.
 *
 * @param {number} a - First number
 * @param {number} b - Second number
 * @returns {number} Difference of a and b
 */
function subtract(a, b) {
  return a - b;
}

/**
 * Async function to fetch data from URL.
 *
 * @param {string} url - The URL to fetch
 * @param {Object} options - Optional fetch options
 * @returns {Promise<Object>} Promise resolving to response data
 */
async function fetchData(url, options = {}) {
  const response = await fetch(url, options);
  return response.json();
}

/**
 * Multiply two numbers using arrow function.
 *
 * @param {number} a - First number
 * @param {number} b - Second number
 * @returns {number} Product of a and b
 */
const multiply = (a, b) => a * b;

/**
 * Async arrow function to delay execution.
 *
 * @param {number} ms - Milliseconds to delay
 * @returns {Promise<void>}
 */
const delay = async (ms) => {
  return new Promise((resolve) => setTimeout(resolve, ms));
};

/**
 * Base class for services.
 */
class BaseService {
  /**
   * Create a new service instance.
   *
   * @param {string} name - Service name
   */
  constructor(name) {
    this.name = name;
    this.status = ServiceStatus.IDLE;
  }

  /**
   * Get the service name.
   *
   * @returns {string} Service name
   */
  getName() {
    return this.name;
  }

  /**
   * Get the current status.
   *
   * @returns {string} Current service status
   */
  getStatus() {
    return this.status;
  }

  /**
   * Start the service.
   *
   * @returns {Promise<void>}
   */
  async start() {
    this.status = ServiceStatus.RUNNING;
  }

  /**
   * Stop the service.
   *
   * @returns {Promise<void>}
   */
  async stop() {
    this.status = ServiceStatus.STOPPED;
  }
}

/**
 * Configured service with additional features.
 *
 * @extends BaseService
 */
class ConfiguredService extends BaseService {
  /**
   * Create a configured service.
   *
   * @param {Object} config - Service configuration
   * @param {string} config.name - Service name
   * @param {string} config.baseUrl - Base URL for API calls
   * @param {number} [config.timeout=30000] - Request timeout
   */
  constructor(config) {
    super(config.name);
    this.config = config;
    this.emitter = new EventEmitter();
    this.timeout = config.timeout || DEFAULT_TIMEOUT;
  }

  /**
   * Get the service configuration.
   *
   * @returns {Object} Current configuration
   */
  getConfig() {
    return { ...this.config };
  }

  /**
   * Update configuration options.
   *
   * @param {Object} updates - Partial configuration updates
   */
  updateConfig(updates) {
    this.config = { ...this.config, ...updates };
    this.emitter.emit("configChanged", this.config);
  }

  /**
   * Subscribe to service events.
   *
   * @param {string} event - Event name
   * @param {Function} callback - Event handler callback
   */
  on(event, callback) {
    this.emitter.on(event, callback);
  }

  /**
   * Static factory method.
   *
   * @param {Object} config - Configuration object
   * @returns {ConfiguredService} New service instance
   */
  static fromConfig(config) {
    return new ConfiguredService(config);
  }
}

/**
 * Simple logger class.
 */
class Logger {
  /**
   * Create a logger.
   *
   * @param {string} prefix - Log message prefix
   */
  constructor(prefix = "") {
    this.prefix = prefix;
  }

  /**
   * Log an info message.
   *
   * @param {string} message - Message to log
   */
  info(message) {
    console.info(`${this.prefix}[INFO] ${message}`);
  }

  /**
   * Log an error message.
   *
   * @param {string} message - Message to log
   */
  error(message) {
    console.error(`${this.prefix}[ERROR] ${message}`);
  }
}

// Export for CommonJS
module.exports = {
  DEFAULT_TIMEOUT,
  MAX_RETRIES,
  ServiceStatus,
  add,
  subtract,
  fetchData,
  multiply,
  delay,
  BaseService,
  ConfiguredService,
  Logger,
};
