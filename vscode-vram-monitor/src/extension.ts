import * as vscode from "vscode";
import { VRAMMonitor } from "./vramMonitor";
import { StatusBarManager } from "./statusBar";
import { OllamaService } from "./ollamaService";
import { DashboardProvider } from "./webview/dashboardProvider";
import { ConfigManager } from "./utils/config";

let vramMonitor: VRAMMonitor | null = null;
let statusBarManager: StatusBarManager | null = null;
let ollamaService: OllamaService | null = null;
let dashboardProvider: DashboardProvider | null = null;

export async function activate(
  context: vscode.ExtensionContext,
): Promise<void> {
  console.log("VRAM Monitor extension is now active");

  const configManager = new ConfigManager(context);

  try {
    vramMonitor = new VRAMMonitor(context, configManager);
    vramMonitor.start();
    console.log("VRAM monitor service started");
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error("Failed to initialize VRAM monitor:", errorMessage);
    vscode.window.showWarningMessage(
      `VRAM Monitor: Failed to initialize - ${errorMessage}`,
    );
  }

  if (vramMonitor) {
    statusBarManager = new StatusBarManager(configManager);
    statusBarManager.subscribe(vramMonitor);
    context.subscriptions.push(statusBarManager);
  }

  context.subscriptions.push({ dispose: () => vramMonitor?.dispose() });

  try {
    ollamaService = new OllamaService(context, configManager);
    const healthy = await ollamaService.checkHealth();
    if (healthy) {
      console.log("Ollama service is available");
    } else {
      console.warn(
        "Ollama service is not available - model management features will be limited",
      );
    }
    context.subscriptions.push(ollamaService);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.warn("Failed to initialize Ollama service:", message);
    ollamaService = null;
  }

  if (vramMonitor && ollamaService) {
    dashboardProvider = new DashboardProvider(
      context,
      vramMonitor,
      ollamaService,
      configManager,
    );
    const providerDisposable = vscode.window.registerWebviewViewProvider(
      DashboardProvider.viewType,
      dashboardProvider,
    );
    context.subscriptions.push(providerDisposable);
  }

  const refreshStatsCommand = vscode.commands.registerCommand(
    "vramMonitor.refreshStats",
    async () => {
      if (vramMonitor) {
        await vramMonitor.refresh();
        const data = vramMonitor.getData();
        if (data.gpu) {
          const modelCount = Array.isArray(data.loaded_models)
            ? data.loaded_models.length
            : 0;
          vscode.window.showInformationMessage(
            `VRAM: ${data.gpu.used_mb}/${data.gpu.total_mb}MB used (${modelCount} models loaded)`,
          );
        } else {
          vscode.window.showWarningMessage(
            "VRAM Monitor: No GPU data available",
          );
        }
      } else {
        vscode.window.showWarningMessage(
          "VRAM Monitor: Service not initialized",
        );
      }
    },
  );

  const toggleStatusBarCommand = vscode.commands.registerCommand(
    "vramMonitor.toggleStatusBar",
    () => {
      if (!statusBarManager) {
        vscode.window.showWarningMessage(
          "VRAM Monitor: Status bar is not available yet",
        );
        return;
      }
      statusBarManager.toggle();
      const visibility = statusBarManager.isShowing() ? "shown" : "hidden";
      vscode.window.showInformationMessage(`VRAM Status Bar ${visibility}`);
    },
  );

  const showOutputCommand = vscode.commands.registerCommand(
    "vramMonitor.showOutput",
    () => {
      vramMonitor?.showOutput();
    },
  );

  const showDiagnosticsCommand = vscode.commands.registerCommand(
    "vramMonitor.showDiagnostics",
    () => {
      if (vramMonitor) {
        const diagnostics = vramMonitor.getDiagnostics();
        const outputChannel = vscode.window.createOutputChannel(
          "VRAM Monitor Diagnostics",
        );
        outputChannel.appendLine("=== VRAM Monitor Diagnostics ===");
        outputChannel.appendLine(`Is Polling: ${diagnostics.isPolling}`);
        outputChannel.appendLine(
          `Poll Interval: ${diagnostics.pollInterval}ms`,
        );
        outputChannel.appendLine(
          `Last Poll Time: ${diagnostics.lastPollTime ? new Date(diagnostics.lastPollTime).toISOString() : "Never"}`,
        );
        outputChannel.appendLine(
          `Last Poll Duration: ${diagnostics.lastPollDuration}ms`,
        );
        outputChannel.appendLine(
          `Last Error: ${diagnostics.lastError || "None"}`,
        );
        outputChannel.appendLine("");
        outputChannel.appendLine("=== Configuration ===");
        outputChannel.appendLine(
          `Python Path: ${diagnostics.config.pythonPath}`,
        );
        outputChannel.appendLine(
          `VRAM Manager Path: ${diagnostics.config.vramManagerPath}`,
        );
        outputChannel.appendLine("");
        outputChannel.appendLine("=== Cached Data ===");
        outputChannel.appendLine(
          JSON.stringify(diagnostics.cachedData, null, 2),
        );
        outputChannel.show();
      } else {
        vscode.window.showWarningMessage(
          "VRAM Monitor: Service not initialized",
        );
      }
    },
  );

  const showDashboardCommand = vscode.commands.registerCommand(
    "vramMonitor.showDashboard",
    () => {
      if (dashboardProvider) {
        dashboardProvider.reveal(true);
      } else {
        vscode.window.showWarningMessage("VRAM dashboard is not ready yet");
      }
    },
  );

  const loadModelCommand = vscode.commands.registerCommand(
    "vramMonitor.loadModel",
    async () => {
      if (!ollamaService) {
        vscode.window.showWarningMessage("Ollama service is not configured");
        return;
      }

      let models;
      try {
        models = await ollamaService.listModels();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(
          `Failed to list Ollama models: ${message}`,
        );
        return;
      }

      if (models.length === 0) {
        vscode.window.showWarningMessage("No Ollama models available");
        return;
      }

      const quickPick = await vscode.window.showQuickPick(
        models.map((model) => ({
          label: model.name,
          description: `${formatBytes(model.size)}`,
        })),
        { placeHolder: "Select a model to load into Ollama" },
      );

      if (!quickPick) {
        return;
      }

      try {
        await ollamaService.loadModel(quickPick.label);
        vscode.window.showInformationMessage(
          `Model ${quickPick.label} loading initiated`,
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(
          `Failed to load ${quickPick.label}: ${message}`,
        );
      }
    },
  );

  const unloadAllModelsCommand = vscode.commands.registerCommand(
    "vramMonitor.unloadAllModels",
    async () => {
      if (!ollamaService) {
        vscode.window.showWarningMessage("Ollama service is not configured");
        return;
      }

      try {
        const count = await ollamaService.unloadAllModels();
        vscode.window.showInformationMessage(`Unloaded ${count} model(s)`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(`Failed to unload models: ${message}`);
      }
    },
  );

  const showOllamaDiagnosticsCommand = vscode.commands.registerCommand(
    "vramMonitor.showOllamaDiagnostics",
    async () => {
      if (!ollamaService) {
        vscode.window.showWarningMessage("Ollama service is not configured");
        return;
      }

      let available;
      try {
        available = await ollamaService.listModels();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(
          `Failed to retrieve available models: ${message}`,
        );
        return;
      }

      let loaded;
      try {
        loaded = await ollamaService.listLoadedModels();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(
          `Failed to retrieve loaded models: ${message}`,
        );
        return;
      }

      const diagnostics = vscode.window.createOutputChannel(
        "Ollama Service Diagnostics",
      );
      const healthy = await ollamaService.checkHealth();
      const config = ollamaService.getConfig();

      diagnostics.appendLine("=== Ollama Service Diagnostics ===");
      diagnostics.appendLine(`Base URL: ${config.baseUrl}`);
      diagnostics.appendLine(
        `Health Status: ${healthy ? "Connected" : "Disconnected"}`,
      );
      diagnostics.appendLine(`Available Models: ${available.length}`);
      diagnostics.appendLine(`Loaded Models: ${loaded.length}`);
      loaded.forEach((model) =>
        diagnostics.appendLine(
          `  - ${model.name} (${formatBytes(model.size_vram)} VRAM)`,
        ),
      );
      diagnostics.appendLine("");
      diagnostics.appendLine("=== Configuration ===");
      diagnostics.appendLine(`Ollama URL: ${config.baseUrl}`);
      diagnostics.appendLine(`Load Timeout: ${config.loadTimeout}ms`);
      diagnostics.appendLine(
        `Health Check Timeout: ${config.healthCheckTimeout}ms`,
      );
      diagnostics.appendLine("");
      diagnostics.appendLine(
        `Last Error: ${ollamaService.getLastError() ?? "None"}`,
      );
      diagnostics.show();
    },
  );

  context.subscriptions.push(refreshStatsCommand);
  context.subscriptions.push(toggleStatusBarCommand);
  context.subscriptions.push(showOutputCommand);
  context.subscriptions.push(showDiagnosticsCommand);
  context.subscriptions.push(showDashboardCommand);
  context.subscriptions.push(loadModelCommand);
  context.subscriptions.push(unloadAllModelsCommand);
  context.subscriptions.push(showOllamaDiagnosticsCommand);
}

export function deactivate(): undefined {
  console.log("VRAM Monitor extension is deactivating");

  if (vramMonitor) {
    vramMonitor.stop();
    vramMonitor.dispose();
    vramMonitor = null;
  }

  if (statusBarManager) {
    statusBarManager.dispose();
    statusBarManager = null;
  }

  if (ollamaService) {
    ollamaService.dispose();
    ollamaService = null;
  }

  if (dashboardProvider) {
    dashboardProvider.dispose();
    dashboardProvider = null;
  }

  return undefined;
}

export function getOllamaService(): OllamaService | null {
  return ollamaService;
}

function formatBytes(bytes: number): string {
  const safeBytes = Number.isFinite(bytes) && bytes >= 0 ? bytes : 0;
  const mb = safeBytes / (1024 * 1024);
  const gb = safeBytes / (1024 * 1024 * 1024);

  if (safeBytes >= 1024 * 1024 * 1024) {
    return `${gb.toFixed(1)}GB`;
  }
  return `${mb.toFixed(1)}MB`;
}
