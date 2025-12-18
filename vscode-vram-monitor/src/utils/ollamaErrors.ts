export interface OllamaErrorOptions {
    url?: string;
    statusCode?: number;
    responseBody?: unknown;
    cause?: Error;
    timeout?: number;
    code?: string;
    model?: string;
}

export class OllamaServiceError extends Error {
    public readonly url?: string;
    public readonly statusCode?: number;
    public readonly responseBody?: unknown;

    constructor(message: string, options: OllamaErrorOptions = {}) {
        super(message);
        this.name = 'OllamaServiceError';
        this.url = options.url;
        this.statusCode = options.statusCode;
        this.responseBody = options.responseBody;
        if (options.cause) {
            this.stack += `\nCaused by: ${options.cause.stack ?? options.cause.message}`;
        }
    }
}

export class OllamaConnectionError extends OllamaServiceError {
    public readonly code?: string;

    constructor(message: string, options: OllamaErrorOptions = {}) {
        super(message, options);
        this.name = 'OllamaConnectionError';
        this.code = options.code;
    }
}

export class OllamaTimeoutError extends OllamaServiceError {
    public readonly timeout: number;

    constructor(timeout: number, options: OllamaErrorOptions = {}) {
        super(`Request timed out after ${timeout}ms`, { ...options, timeout });
        this.name = 'OllamaTimeoutError';
        this.timeout = timeout;
    }
}

export class ModelNotFoundError extends OllamaServiceError {
    constructor(model: string, options: OllamaErrorOptions = {}) {
        super(`Model "${model}" not found`, { ...options, model });
        this.name = 'ModelNotFoundError';
    }
}

export class ModelLoadError extends OllamaServiceError {
    constructor(model: string, options: OllamaErrorOptions = {}) {
        super(`Failed to load model "${model}"`, { ...options, model });
        this.name = 'ModelLoadError';
    }
}

export class ModelUnloadError extends OllamaServiceError {
    constructor(model: string, options: OllamaErrorOptions = {}) {
        super(`Failed to unload model "${model}"`, { ...options, model });
        this.name = 'ModelUnloadError';
    }
}

export class InvalidResponseError extends OllamaServiceError {
    constructor(responseBody: unknown, options: OllamaErrorOptions = {}) {
        super('Invalid response from Ollama API', { ...options, responseBody });
        this.name = 'InvalidResponseError';
    }
}
