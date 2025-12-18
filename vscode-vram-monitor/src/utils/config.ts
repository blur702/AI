import * as fs from 'fs';
import * as vscode from 'vscode';

export interface VRAMMonitorConfig {
    pythonPath: string;
    vramManagerPath: string;
    pollInterval: number;
    ollamaUrl: string;
    ollamaLoadTimeout: number;
    ollamaHealthCheckTimeout: number;
    showTotalVRAM: boolean;
    showUsedVRAM: boolean;
    showFreeVRAM: boolean;
    showUtilization: boolean;
    showLoadedModels: boolean;
    showGPUProcesses: boolean;
    showGPUName: boolean;
    showProgressBar: boolean;
}

export class ConfigManager implements vscode.Disposable {
    private config: VRAMMonitorConfig;
    private readonly outputChannel: vscode.OutputChannel;
    private readonly emitter: vscode.EventEmitter<vscode.ConfigurationChangeEvent>;
    private readonly watcher: vscode.Disposable;

    constructor(private readonly context: vscode.ExtensionContext) {
        this.outputChannel = vscode.window.createOutputChannel('VRAM Monitor Config');
        this.emitter = new vscode.EventEmitter<vscode.ConfigurationChangeEvent>();
        this.config = this.loadConfiguration();

        this.watcher = vscode.workspace.onDidChangeConfiguration((event) => {
            if (!event.affectsConfiguration('vramMonitor')) {
                return;
            }
            const previous = this.config;
            this.config = this.loadConfiguration();
            this.logConfigChanges(previous, this.config);
            this.emitter.fire(event);
        });

        this.context.subscriptions.push(this);
    }

    getConfig(): VRAMMonitorConfig {
        return { ...this.config };
    }

    get<K extends keyof VRAMMonitorConfig>(key: K): VRAMMonitorConfig[K] {
        return this.config[key];
    }

    getPythonPaths(): { pythonPath: string; vramManagerPath: string } {
        return {
            pythonPath: this.config.pythonPath,
            vramManagerPath: this.config.vramManagerPath
        };
    }

    get onDidChangeConfiguration(): vscode.Event<vscode.ConfigurationChangeEvent> {
        return this.emitter.event;
    }

    dispose(): void {
        this.watcher.dispose();
        this.emitter.dispose();
        this.outputChannel.dispose();
    }

    private loadConfiguration(): VRAMMonitorConfig {
        const settings = vscode.workspace.getConfiguration('vramMonitor');

        const pythonPathRaw = settings.get<string>('pythonPath', 'python')?.trim() ?? 'python';
        const vramManagerRaw = settings.get<string>('vramManagerPath', '${workspaceFolder}/vram_manager.py')?.trim() ??
            '${workspaceFolder}/vram_manager.py';
        const pollIntervalRaw = settings.get<number>('pollInterval', 3000);
        const ollamaUrl = settings.get<string>('ollamaUrl', 'http://localhost:11434') ?? 'http://localhost:11434';
        const ollamaLoadTimeoutRaw = settings.get<number>('ollamaLoadTimeout', 60000);
        const ollamaHealthCheckTimeoutRaw = settings.get<number>('ollamaHealthCheckTimeout', 5000);

        const pythonPath = this.resolvePath(pythonPathRaw, 'python');
        const vramManagerPath = this.resolvePath(vramManagerRaw, '${workspaceFolder}/vram_manager.py');
        const pollInterval = this.clampNumber(pollIntervalRaw, 3000, 1000);
        const ollamaLoadTimeout = this.clampNumber(ollamaLoadTimeoutRaw, 60000, 5000);
        const ollamaHealthCheckTimeout = this.clampNumber(ollamaHealthCheckTimeoutRaw, 5000, 1000);

        if (!fs.existsSync(vramManagerPath)) {
            this.outputChannel.appendLine(`[${new Date().toISOString()}] Warning: vram_manager.py not found at ${vramManagerPath}`);
        }

        return {
            pythonPath,
            vramManagerPath,
            pollInterval,
            ollamaUrl,
            ollamaLoadTimeout,
            ollamaHealthCheckTimeout,
            showTotalVRAM: settings.get<boolean>('showTotalVRAM', true),
            showUsedVRAM: settings.get<boolean>('showUsedVRAM', true),
            showFreeVRAM: settings.get<boolean>('showFreeVRAM', true),
            showUtilization: settings.get<boolean>('showUtilization', true),
            showLoadedModels: settings.get<boolean>('showLoadedModels', true),
            showGPUProcesses: settings.get<boolean>('showGPUProcesses', true),
            showGPUName: settings.get<boolean>('showGPUName', true),
            showProgressBar: settings.get<boolean>('showProgressBar', true)
        };
    }

    private resolvePath(candidate: string | undefined, fallback: string): string {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        const baseFolder = workspaceFolder ? workspaceFolder.uri.fsPath : '';
        const raw = candidate || fallback;
        return raw.replace(/\$\{workspaceFolder\}/g, baseFolder);
    }

    private clampNumber(value: number | undefined, fallback: number, minimum: number): number {
        const normalized = Number.isFinite(value) ? value! : fallback;
        const clamped = Math.max(minimum, normalized);
        if (clamped !== normalized) {
            this.outputChannel.appendLine(`[${new Date().toISOString()}] Warning: Clamped value from ${normalized} to ${clamped}`);
        }
        return clamped;
    }

    private logConfigChanges(previous: VRAMMonitorConfig, current: VRAMMonitorConfig): void {
        const changes: string[] = [];
        for (const key of Object.keys(current) as (keyof VRAMMonitorConfig)[]) {
            if (previous[key] !== current[key]) {
                changes.push(`${key}: ${previous[key]} -> ${current[key]}`);
            }
        }
        if (changes.length > 0) {
            this.outputChannel.appendLine(`[${new Date().toISOString()}] Configuration changed:`);
            changes.forEach((change) => this.outputChannel.appendLine(`  ${change}`));
        }
    }
}
