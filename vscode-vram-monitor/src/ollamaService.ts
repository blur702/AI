import * as vscode from 'vscode';
import { httpRequest } from './utils/httpClient';
import { OllamaModelInfo, OllamaLoadedModel, OllamaTagsResponse, OllamaPsResponse, isOllamaTagsResponse, isOllamaPsResponse } from './types/ollamaTypes';
import { OllamaConnectionError, OllamaTimeoutError, OllamaServiceError, ModelNotFoundError, ModelLoadError, ModelUnloadError, InvalidResponseError } from './utils/ollamaErrors';
import { ConfigManager } from './utils/config';

export interface OllamaServiceConfig {
    baseUrl: string;
    loadTimeout: number;
    healthCheckTimeout: number;
}

export interface LoadModelOptions {
    keepAlive?: number;
}

export class OllamaService implements vscode.Disposable {
    private readonly outputChannel: vscode.OutputChannel;
    private config: OllamaServiceConfig;
    private lastError: string | null = null;
    private readonly configWatcher: vscode.Disposable;

    constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly configManager: ConfigManager
    ) {
        this.outputChannel = vscode.window.createOutputChannel('Ollama Service');
        this.config = this.buildServiceConfig();

        this.configWatcher = this.configManager.onDidChangeConfiguration((event) => {
            if (
                event.affectsConfiguration('vramMonitor.ollamaUrl') ||
                event.affectsConfiguration('vramMonitor.ollamaLoadTimeout') ||
                event.affectsConfiguration('vramMonitor.ollamaHealthCheckTimeout')
            ) {
                this.config = this.buildServiceConfig();
                this.log('Ollama configuration reloaded');
            }
        });

        this.context.subscriptions.push(this.outputChannel);
        this.context.subscriptions.push(this.configWatcher);
        this.log('Ollama service initialized');
    }

    getConfig(): OllamaServiceConfig {
        return { ...this.config };
    }

    getLastError(): string | null {
        return this.lastError;
    }

    async checkHealth(timeout?: number): Promise<boolean> {
        try {
            const response = await httpRequest<unknown>({
                url: `${this.config.baseUrl}/api/tags`,
                method: 'GET',
                timeout: timeout ?? this.config.healthCheckTimeout
            });

            if (!isOllamaTagsResponse(response)) {
                throw new InvalidResponseError(response, { url: `${this.config.baseUrl}/api/tags` });
            }

            this.lastError = null;
            this.log('Ollama health check succeeded');
            return true;
        } catch (error) {
            this.recordError(error, 'Health check failed');
            return false;
        }
    }

    async listModels(timeout?: number): Promise<OllamaModelInfo[]> {
        try {
            const response = await httpRequest<unknown>({
                url: `${this.config.baseUrl}/api/tags`,
                method: 'GET',
                timeout: timeout ?? this.config.loadTimeout
            });

            if (!isOllamaTagsResponse(response)) {
                throw new InvalidResponseError(response, { url: `${this.config.baseUrl}/api/tags` });
            }

            this.lastError = null;
            return (response as OllamaTagsResponse).models;
        } catch (error) {
            if (error instanceof OllamaConnectionError || error instanceof OllamaTimeoutError) {
                this.recordError(error, 'Listing models failed');
                return [];
            }
            this.recordError(error, 'Listing models failed');
            throw error;
        }
    }

    async listLoadedModels(timeout?: number): Promise<OllamaLoadedModel[]> {
        try {
            const response = await httpRequest<unknown>({
                url: `${this.config.baseUrl}/api/ps`,
                method: 'GET',
                timeout: timeout ?? this.config.healthCheckTimeout
            });

            if (!isOllamaPsResponse(response)) {
                throw new InvalidResponseError(response, { url: `${this.config.baseUrl}/api/ps` });
            }

            this.lastError = null;
            return (response as OllamaPsResponse).models;
        } catch (error) {
            if (error instanceof OllamaConnectionError || error instanceof OllamaTimeoutError) {
                this.recordError(error, 'Listing loaded models failed');
                return [];
            }
            this.recordError(error, 'Listing loaded models failed');
            throw error;
        }
    }

    async loadModel(modelName: string, options?: LoadModelOptions): Promise<boolean> {
        const payload = {
            model: modelName,
            prompt: '',
            keep_alive: options?.keepAlive ?? -1,
            stream: false
        };

        try {
            this.log(`Loading model ${modelName}...`);
            await httpRequest({
                url: `${this.config.baseUrl}/api/generate`,
                method: 'POST',
                body: payload,
                timeout: this.config.loadTimeout
            });

            this.lastError = null;
            this.log(`Model ${modelName} loaded`);
            return true;
        } catch (error) {
            this.recordError(error, `Loading model ${modelName} failed`);

            if (error instanceof OllamaServiceError && error.statusCode === 404) {
                throw new ModelNotFoundError(modelName, { cause: error instanceof Error ? error : undefined });
            }

            if (error instanceof OllamaTimeoutError) {
                throw error;
            }

            if (error instanceof OllamaConnectionError) {
                throw error;
            }

            throw new ModelLoadError(modelName, { cause: error instanceof Error ? error : undefined });
        }
    }

    async unloadModel(modelName: string, timeout?: number): Promise<boolean> {
        const payload = {
            model: modelName,
            prompt: '',
            keep_alive: 0,
            stream: false
        };

        try {
            this.log(`Unloading model ${modelName}...`);
            await httpRequest({
                url: `${this.config.baseUrl}/api/generate`,
                method: 'POST',
                body: payload,
                timeout: timeout ?? 30000
            });

            this.lastError = null;
            this.log(`Model ${modelName} unloaded`);
            return true;
        } catch (error) {
            this.recordError(error, `Unloading model ${modelName} failed`);

            if (error instanceof OllamaConnectionError || error instanceof OllamaTimeoutError) {
                throw error;
            }

            throw new ModelUnloadError(modelName, { cause: error instanceof Error ? error : undefined });
        }
    }

    async unloadAllModels(): Promise<number> {
        const models = await this.listLoadedModels();
        let unloaded = 0;

        for (const model of models) {
            try {
                const success = await this.unloadModel(model.model, 30000);
                if (success) {
                    unloaded += 1;
                }
            } catch (error) {
                this.log(`Failed to unload ${model.model}: ${error instanceof Error ? error.message : String(error)}`);
            }
        }

        this.log(`Unloaded ${unloaded} model(s)`);
        return unloaded;
    }

    showOutput(): void {
        this.outputChannel.show();
    }

    dispose(): void {
        this.configWatcher.dispose();
        this.outputChannel.dispose();
    }

    private buildServiceConfig(): OllamaServiceConfig {
        const settings = this.configManager.getConfig();
        let baseUrl = settings.ollamaUrl.trim();

        if (!baseUrl.startsWith('http://') && !baseUrl.startsWith('https://')) {
            baseUrl = `http://${baseUrl}`;
        }

        return {
            baseUrl,
            loadTimeout: settings.ollamaLoadTimeout,
            healthCheckTimeout: settings.ollamaHealthCheckTimeout
        };
    }

    private recordError(error: unknown, message: string): void {
        const debugMessage = error instanceof Error ? `${message}: ${error.message}` : `${message}: ${String(error)}`;
        this.log(debugMessage);
        this.lastError = error instanceof Error ? error.message : String(error);
    }

    private log(message: string): void {
        const timestamp = new Date().toISOString();
        this.outputChannel.appendLine(`[${timestamp}] ${message}`);
    }
}
