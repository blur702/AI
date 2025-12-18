import * as vscode from 'vscode';
import { VRAMData, EMPTY_VRAM_DATA } from './types/vramTypes';
import { fetchVRAMData, FetchResult } from './utils/vramDataFetcher';
import { ConfigManager } from './utils/config';

/**
 * Maximum timeout for a single Python script execution (10 seconds).
 * This bounds the timeout independently of pollInterval to prevent
 * unreasonably long waits even if pollInterval is set to a large value.
 */
const MAX_TIMEOUT_MS = 10000;

export interface VRAMMonitorDiagnostics {
    isPolling: boolean;
    pollInterval: number;
    lastPollTime: number;
    lastPollDuration: number;
    lastError: string | null;
    cachedData: VRAMData;
    config: { pythonPath: string; vramManagerPath: string };
}

/**
 * VRAM Monitor service that polls vram_manager.py at configurable intervals
 * and caches the results for fast access
 */
export class VRAMMonitor implements vscode.Disposable {
    private pollTimer: NodeJS.Timeout | null = null;
    private cachedData: VRAMData = EMPTY_VRAM_DATA;
    private isPolling = false;
    private pollInterval = 3000;
    private lastPollTime = 0;
    private lastPollDuration = 0;
    private lastError: string | null = null;
    private hasShownPythonWarning = false;
    private hasShownVRAMManagerWarning = false;

    private readonly onDataChangedEmitter = new vscode.EventEmitter<VRAMData>();
    public readonly onDataChanged = this.onDataChangedEmitter.event;

    private configChangeSubscription: vscode.Disposable | null = null;
    private readonly outputChannel: vscode.OutputChannel;

    constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly configManager: ConfigManager
    ) {
        this.outputChannel = vscode.window.createOutputChannel('VRAM Monitor');
        this.refreshPollInterval();
        this.setupConfigurationWatcher();
    }

    private refreshPollInterval(): void {
        const raw = this.configManager.get('pollInterval');
        const sanitized = Math.max(1000, Number.isFinite(raw) ? raw : 3000);
        if (sanitized !== raw) {
            this.log(`Adjusted pollInterval from ${raw} to ${sanitized}`);
        }
        this.pollInterval = sanitized;
        this.log(`Configuration loaded: pollInterval=${this.pollInterval}ms`);
    }

    /**
     * Sets up a watcher for configuration changes
     */
    private setupConfigurationWatcher(): void {
        this.configChangeSubscription = this.configManager.onDidChangeConfiguration((event) => {
            const relevant =
                event.affectsConfiguration('vramMonitor.pollInterval') ||
                event.affectsConfiguration('vramMonitor.pythonPath') ||
                event.affectsConfiguration('vramMonitor.vramManagerPath');

            if (!relevant) {
                return;
            }

            this.log('Configuration changed, reloading...');
            const wasPolling = this.isPolling;
            if (wasPolling) {
                this.stop();
            }

            this.refreshPollInterval();

            if (event.affectsConfiguration('vramMonitor.pythonPath')) {
                this.hasShownPythonWarning = false;
            }
            if (event.affectsConfiguration('vramMonitor.vramManagerPath')) {
                this.hasShownVRAMManagerWarning = false;
            }

            if (wasPolling) {
                this.start();
            }
        });
    }

    /**
     * Logs a message to the output channel with timestamp
     */
    private log(message: string): void {
        const timestamp = new Date().toISOString();
        this.outputChannel.appendLine(`[${timestamp}] ${message}`);
    }

    /**
     * Starts the polling loop
     */
    start(): void {
        if (this.isPolling) {
            this.log('Monitor already running, ignoring start request');
            return;
        }

        const paths = this.configManager.getPythonPaths();
        this.log(`Starting VRAM monitor with interval ${this.pollInterval}ms`);
        this.log(`Python path: ${paths.pythonPath}`);
        this.log(`VRAM manager path: ${paths.vramManagerPath}`);

        this.isPolling = true;

        // Perform initial poll immediately
        this.poll();

        // Set up interval for subsequent polls
        this.pollTimer = setInterval(() => {
            this.poll();
        }, this.pollInterval);
    }

    /**
     * Stops the polling loop
     */
    stop(): void {
        if (!this.isPolling) {
            this.log('Monitor not running, ignoring stop request');
            return;
        }

        this.log('Stopping VRAM monitor');
        if (this.pollTimer !== null) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.isPolling = false;
    }

    /**
     * Performs a single poll cycle.
     * Timeout is bounded by MAX_TIMEOUT_MS to prevent unreasonably long waits.
     */
    private async poll(): Promise<void> {
        const startTime = Date.now();
        // Bound the timeout to MAX_TIMEOUT_MS regardless of pollInterval
        const timeout = Math.min(this.pollInterval * 1.5, MAX_TIMEOUT_MS);

        try {
            const paths = this.configManager.getPythonPaths();
            const result = await fetchVRAMData(paths, { timeout });
            this.handleFetchResult(result);
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            this.log(`Unexpected error during poll: ${errorMessage}`);
            this.lastError = errorMessage;
        }

        this.lastPollTime = Date.now();
        this.lastPollDuration = this.lastPollTime - startTime;

        // Warn if poll takes longer than interval
        if (this.lastPollDuration > this.pollInterval) {
            this.log(`WARNING: Poll took ${this.lastPollDuration}ms, longer than interval ${this.pollInterval}ms`);
        }
    }

    /**
     * Handles the result of a fetch operation
     */
    private handleFetchResult(result: FetchResult): void {
        if (result.success) {
            this.cachedData = result.data;
            this.lastError = null;
            this.onDataChangedEmitter.fire(this.cachedData);

            // Log summary
            const gpu = result.data.gpu;
            if (gpu) {
                const usedPct = ((gpu.used_mb / gpu.total_mb) * 100).toFixed(1);
                this.log(
                    `Poll success: ${gpu.name} - ${gpu.used_mb}/${gpu.total_mb}MB (${usedPct}%) - ${result.data.loaded_models.length} models loaded`
                );
            } else {
                this.log('Poll success: No GPU data available');
            }
        } else {
            this.lastError = result.error || 'Unknown error';
            this.log(`Poll failed: ${this.lastError}`);

            // Show one-time warnings for missing dependencies
            if (result.errorType === 'python_not_found' && !this.hasShownPythonWarning) {
                this.hasShownPythonWarning = true;
                vscode.window.showWarningMessage(
                    'VRAM Monitor: Python not found. Please configure vramMonitor.pythonPath setting.'
                );
            }

            if (result.errorType === 'vram_manager_not_found' && !this.hasShownVRAMManagerWarning) {
                this.hasShownVRAMManagerWarning = true;
                vscode.window.showWarningMessage(
                    'VRAM Monitor: vram_manager.py not found. Please configure vramMonitor.vramManagerPath setting.'
                );
            }
        }
    }

    /**
     * Forces an immediate refresh outside the regular poll interval
     */
    async refresh(): Promise<void> {
        this.log('Manual refresh requested');
        await this.poll();
    }

    /**
     * Returns a deep copy of the cached VRAM data
     */
    getData(): VRAMData {
        return JSON.parse(JSON.stringify(this.cachedData));
    }

    /**
     * Returns diagnostic information about the monitor
     */
    getDiagnostics(): VRAMMonitorDiagnostics {
        return {
            isPolling: this.isPolling,
            pollInterval: this.pollInterval,
            lastPollTime: this.lastPollTime,
            lastPollDuration: this.lastPollDuration,
            lastError: this.lastError,
            cachedData: this.getData(),
            config: this.configManager.getPythonPaths()
        };
    }

    /**
     * Shows the output channel
     */
    showOutput(): void {
        this.outputChannel.show();
    }

    /**
     * Disposes of all resources
     */
    dispose(): void {
        this.stop();
        if (this.configChangeSubscription) {
            this.configChangeSubscription.dispose();
            this.configChangeSubscription = null;
        }
        this.onDataChangedEmitter.dispose();
        this.outputChannel.dispose();
    }
}
