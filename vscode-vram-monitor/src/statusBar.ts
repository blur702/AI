import * as vscode from "vscode";
import { VRAMData, GPUInfo, GPUAggregate } from "./types/vramTypes";
import { VRAMMonitor } from "./vramMonitor";
import { ConfigManager, VRAMMonitorConfig } from "./utils/config";

const STATUS_BAR_COMMAND = "vramMonitor.showDashboard";

export class StatusBarManager implements vscode.Disposable {
  private readonly statusBarItem: vscode.StatusBarItem;
  private readonly outputChannel: vscode.OutputChannel;
  private readonly configSubscription: vscode.Disposable;
  private dataSubscription: vscode.Disposable | null = null;
  private isVisible = true;
  private lastText: string | null = null;
  private lastTooltip: string | null = null;
  private lastColorId: string | undefined = undefined;
  private latestData: VRAMData | null = null;

  constructor(private readonly configManager: ConfigManager) {
    this.outputChannel = vscode.window.createOutputChannel(
      "VRAM Monitor Status",
    );
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100,
    );
    this.statusBarItem.text = "GPU: Loading...";
    this.statusBarItem.tooltip = "VRAM Monitor - Initializing...";
    this.statusBarItem.command = STATUS_BAR_COMMAND;
    this.statusBarItem.show();

    this.configSubscription = this.configManager.onDidChangeConfiguration(
      () => {
        if (this.latestData) {
          this.updateStatusBar(this.latestData);
        }
      },
    );

    this.log("Status bar initialized");
  }

  subscribe(monitor: VRAMMonitor): void {
    if (this.dataSubscription) {
      this.dataSubscription.dispose();
    }
    this.dataSubscription = monitor.onDataChanged((data) =>
      this.updateStatusBar(data),
    );
    this.log("Subscribed to VRAM monitor updates");
    this.updateStatusBar(monitor.getData());
  }

  show(): void {
    if (this.isVisible) {
      return;
    }
    this.isVisible = true;
    this.statusBarItem.show();
    this.log("Status bar shown");
  }

  hide(): void {
    if (!this.isVisible) {
      return;
    }
    this.isVisible = false;
    this.statusBarItem.hide();
    this.log("Status bar hidden");
  }

  toggle(): void {
    this.isVisible ? this.hide() : this.show();
  }

  isShowing(): boolean {
    return this.isVisible;
  }

  dispose(): void {
    this.dataSubscription?.dispose();
    this.configSubscription.dispose();
    this.statusBarItem.dispose();
    this.outputChannel.dispose();
    this.isVisible = false;
  }

  private updateStatusBar(data: VRAMData): void {
    this.latestData = data;
    const config = this.configManager.getConfig();

    if (!data || !data.gpu) {
      this.applyState(
        "GPU: N/A",
        "No GPU detected or nvidia-smi unavailable",
        undefined,
      );
      return;
    }

    const gpuList: GPUInfo[] = Array.isArray(data.gpu.gpus)
      ? data.gpu.gpus
      : [];
    const aggregate: GPUAggregate = data.gpu.aggregate ?? {
      total_mb: data.gpu.total_mb,
      used_mb: data.gpu.used_mb,
      free_mb: data.gpu.free_mb,
      utilization: data.gpu.utilization ?? 0,
    };

    const totalMb = clampNumber(aggregate.total_mb ?? 0);
    const usedMb = clampNumber(aggregate.used_mb ?? 0);
    const utilization = clampNumber(aggregate.utilization ?? 0);
    const percent = calculatePercent(usedMb, totalMb, utilization);

    const textSegments: string[] = [];

    if (config.showUsedVRAM && config.showTotalVRAM) {
      textSegments.push(`${formatMemory(usedMb)} / ${formatMemory(totalMb)}`);
    } else {
      if (config.showUsedVRAM) {
        textSegments.push(formatMemory(usedMb));
      }
      if (config.showTotalVRAM) {
        textSegments.push(formatMemory(totalMb));
      }
    }

    if (config.showUtilization) {
      textSegments.push(`${formatPercentage(utilization)}%`);
    }

    if (textSegments.length === 0) {
      textSegments.push(`${formatPercentage(percent)}%`);
    }

    const text = `GPU: ${textSegments.join(" · ")}`;
    const tooltipLines = this.buildTooltipLines(
      data,
      gpuList,
      usedMb,
      totalMb,
      percent,
      utilization,
      config,
    );
    const tooltip = tooltipLines.join("\n");
    const backgroundColor = getColorForUtilization(
      utilization !== 0 ? utilization : percent,
    );

    this.applyState(text, tooltip, backgroundColor);
  }

  private buildTooltipLines(
    data: VRAMData,
    gpuList: GPUInfo[],
    usedMb: number,
    totalMb: number,
    percent: number,
    utilization: number,
    config: VRAMMonitorConfig,
  ): string[] {
    const lines: string[] = [];

    const primaryLabel = gpuList[0]?.name ?? data.gpu?.name ?? "Unknown GPU";
    if (config.showGPUName) {
      lines.push(primaryLabel);
    }

    const parts: string[] = [];
    if (config.showUsedVRAM) {
      parts.push(`Used ${formatMemory(usedMb)}`);
    }
    if (config.showTotalVRAM) {
      parts.push(`Total ${formatMemory(totalMb)}`);
    }

    const vramLineParts: string[] = [];
    if (parts.length > 0) {
      vramLineParts.push(`VRAM: ${parts.join(" · ")}`);
    } else {
      vramLineParts.push(`VRAM: ${formatPercentage(percent)}%`);
    }

    if (config.showProgressBar) {
      vramLineParts.push(createProgressBar(percent));
    }

    lines.push(vramLineParts.join(" "));

    if (config.showUtilization) {
      lines.push(`Utilization: ${formatPercentage(utilization)}%`);
    }

    const models = Array.isArray(data.loaded_models) ? data.loaded_models : [];
    if (config.showLoadedModels) {
      lines.push(
        `Loaded Models: ${models.length > 0 ? models.length : "None"}`,
      );
    }

    const processes = Array.isArray(data.gpu_processes)
      ? data.gpu_processes
      : [];
    if (config.showGPUProcesses) {
      lines.push(
        `GPU Processes: ${processes.length > 0 ? processes.length : "None"}`,
      );
    }

    if (gpuList.length > 1) {
      lines.push(`Multi-GPU: ${gpuList.length} GPUs (showing aggregate)`);
      const names = gpuList.map((gpu) => gpu.name).join(", ");
      lines.push(`GPUs: ${names}`);
    }

    lines.push("Click to open dashboard");

    return lines;
  }

  private applyState(
    text: string,
    tooltip: string,
    color: vscode.ThemeColor | undefined,
  ): void {
    const colorId = color?.id;
    const shouldLog =
      text !== this.lastText ||
      tooltip !== this.lastTooltip ||
      colorId !== this.lastColorId;

    this.statusBarItem.text = text;
    this.statusBarItem.tooltip = tooltip;
    this.statusBarItem.backgroundColor = color;

    if (shouldLog) {
      this.log(`Status bar updated: ${text}`);
      this.lastText = text;
      this.lastTooltip = tooltip;
      this.lastColorId = colorId;
    }
  }

  private log(message: string): void {
    const timestamp = new Date().toISOString();
    this.outputChannel.appendLine(`[${timestamp}] ${message}`);
  }
}

function clampNumber(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, value);
}

function formatMemory(mb: number): string {
  const bytes = clampNumber(mb) * 1024 * 1024;
  return formatBytes(bytes);
}

function formatBytes(bytes: number): string {
  const safeBytes = clampNumber(bytes);
  if (safeBytes >= 1024 * 1024 * 1024) {
    return `${(safeBytes / (1024 * 1024 * 1024)).toFixed(1)}GB`;
  }
  if (safeBytes >= 1024 * 1024) {
    return `${(safeBytes / (1024 * 1024)).toFixed(1)}MB`;
  }
  return `${Math.max(0, Math.round(safeBytes))}B`;
}

function formatPercentage(value: number): string {
  const safeValue = clampNumber(value);
  return Math.min(100, safeValue).toFixed(1);
}

function calculatePercent(
  used: number,
  total: number,
  fallback: number,
): number {
  if (total > 0) {
    return Math.min(100, (used / total) * 100);
  }
  return clampNumber(fallback);
}

function createProgressBar(percent: number, length = 10): string {
  const safePercent = Math.min(100, Math.max(0, percent));
  const filledSegments = Math.round((safePercent / 100) * length);
  const emptySegments = Math.max(0, length - filledSegments);
  return `${"█".repeat(filledSegments)}${"░".repeat(emptySegments)}`;
}

function getColorForUtilization(percent: number): vscode.ThemeColor {
  const safePercent = Math.min(100, Math.max(0, percent));
  if (safePercent <= 50) {
    return new vscode.ThemeColor("statusBarItem.prominentBackground");
  }
  if (safePercent <= 80) {
    return new vscode.ThemeColor("statusBarItem.warningBackground");
  }
  return new vscode.ThemeColor("statusBarItem.errorBackground");
}
