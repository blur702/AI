import { promises as fs } from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { VRAMMonitor } from "../vramMonitor";
import { OllamaService } from "../ollamaService";
import { ConfigManager } from "../utils/config";
import { VRAMData } from "../types/vramTypes";
import { OllamaModelInfo, OllamaLoadedModel } from "../types/ollamaTypes";

interface WebviewMessage {
  type: string;
  modelName?: string;
}

interface UpdateDataMessage {
  type: "updateData";
  data: {
    vram: VRAMData;
    available: OllamaModelInfo[];
    loaded: OllamaLoadedModel[];
  };
}

interface ErrorMessage {
  type: "error";
  message: string;
}

interface ModelLoadStartedMessage {
  type: "modelLoadStarted";
  modelName: string;
}

interface ModelUnloadedMessage {
  type: "modelUnloaded";
  modelName: string;
}

interface UpdateSettingsMessage {
  type: "updateSettings";
  settings: {
    showTotalVRAM: boolean;
    showUsedVRAM: boolean;
    showFreeVRAM: boolean;
    showUtilization: boolean;
    showLoadedModels: boolean;
    showGPUProcesses: boolean;
    showGPUName: boolean;
    showProgressBar: boolean;
  };
}

type OutgoingMessage =
  | UpdateDataMessage
  | ErrorMessage
  | ModelLoadStartedMessage
  | ModelUnloadedMessage
  | UpdateSettingsMessage;

export class DashboardProvider
  implements vscode.WebviewViewProvider, vscode.Disposable
{
  public static readonly viewType = "vramMonitor.dashboardView";

  private webviewView?: vscode.WebviewView;
  private readonly disposables: vscode.Disposable[] = [];
  private readonly templatePromise: Promise<string>;
  private isRefreshing = false;
  private refreshScheduled = false;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly monitor: VRAMMonitor,
    private readonly ollamaService: OllamaService,
    private readonly configManager: ConfigManager,
  ) {
    this.templatePromise = this.loadTemplate();
    this.disposables.push(
      this.configManager.onDidChangeConfiguration(() => {
        this.postSettings();
      }),
    );
  }

  async resolveWebviewView(webviewView: vscode.WebviewView): Promise<void> {
    this.webviewView = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
    };

    webviewView.webview.html = await this.getHtmlContent(webviewView.webview);

    this.disposables.push(
      webviewView.webview.onDidReceiveMessage(
        (message: WebviewMessage) => this.handleWebviewMessage(message),
        null,
      ),
    );

    this.disposables.push(
      webviewView.onDidDispose(() => {
        this.webviewView = undefined;
      }, null),
    );

    this.disposables.push(
      this.monitor.onDataChanged(() => {
        void this.refreshData();
      }),
    );

    this.postSettings();
    void this.refreshData();
  }

  reveal(preserveFocus?: boolean): void {
    this.webviewView?.show?.(preserveFocus);
  }

  dispose(): void {
    this.disposables.forEach((disposable) => disposable.dispose());
    this.disposables.length = 0;
    this.webviewView = undefined;
  }

  private async handleWebviewMessage(message: WebviewMessage): Promise<void> {
    switch (message.type) {
      case "ready":
        await this.refreshData();
        break;
      case "refresh":
        await this.refreshData();
        break;
      case "loadModel":
        await this.loadModel(message.modelName!);
        break;
      case "unloadModel":
        await this.unloadModel(message.modelName!);
        break;
    }
  }

  private async refreshData(): Promise<void> {
    if (!this.webviewView || this.isRefreshing) {
      if (this.isRefreshing) {
        this.refreshScheduled = true;
      }
      return;
    }

    this.isRefreshing = true;

    try {
      const vramData = this.monitor.getData();
      const [available, loaded] = await Promise.all([
        this.ollamaService.listModels(),
        this.ollamaService.listLoadedModels(),
      ]);

      this.postMessage({
        type: "updateData",
        data: { vram: vramData, available, loaded },
      });

      this.postSettings();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.postMessage({ type: "error", message });
    } finally {
      this.isRefreshing = false;
      if (this.refreshScheduled) {
        this.refreshScheduled = false;
        void this.refreshData();
      }
    }
  }

  private async loadModel(modelName: string): Promise<void> {
    if (!this.webviewView) {
      return;
    }

    this.postMessage({ type: "modelLoadStarted", modelName });

    try {
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `Loading ${modelName}`,
          cancellable: false,
        },
        async () => {
          await this.ollamaService.loadModel(modelName);
        },
      );
      await this.refreshData();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.postMessage({ type: "error", message });
    }
  }

  private async unloadModel(modelName: string): Promise<void> {
    if (!this.webviewView) {
      return;
    }

    try {
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `Unloading ${modelName}`,
          cancellable: false,
        },
        async () => {
          await this.ollamaService.unloadModel(modelName);
        },
      );
      this.postMessage({ type: "modelUnloaded", modelName });
      await this.refreshData();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.postMessage({ type: "error", message });
    }
  }

  private postMessage(message: OutgoingMessage): void {
    this.webviewView?.webview.postMessage(message);
  }

  private postSettings(): void {
    if (!this.webviewView) {
      return;
    }

    const config = this.configManager.getConfig();
    const settings = {
      showTotalVRAM: config.showTotalVRAM,
      showUsedVRAM: config.showUsedVRAM,
      showFreeVRAM: config.showFreeVRAM,
      showUtilization: config.showUtilization,
      showLoadedModels: config.showLoadedModels,
      showGPUProcesses: config.showGPUProcesses,
      showGPUName: config.showGPUName,
      showProgressBar: config.showProgressBar,
    };

    this.postMessage({ type: "updateSettings", settings });
  }

  private async getHtmlContent(webview: vscode.Webview): Promise<string> {
    const template = await this.templatePromise;
    const nonce = getNonce();

    return template
      .replace(/{{nonce}}/g, nonce)
      .replace(/{{cspSource}}/g, webview.cspSource);
  }

  private loadTemplate(): Promise<string> {
    const htmlPath = path.join(
      this.context.extensionUri.fsPath,
      "src",
      "webview",
      "dashboard.html",
    );
    return fs.readFile(htmlPath, { encoding: "utf8" });
  }
}

function getNonce(): string {
  let text = "";
  const possible =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
