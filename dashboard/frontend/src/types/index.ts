export type ServiceStatus = 'stopped' | 'starting' | 'running' | 'stopping' | 'error';

export interface ServiceConfig {
  id: string;
  name: string;
  port: number;
  icon: string;
  description: string;
  tags: string[];
  cardClass: string;
  section: 'main' | 'music';
  external?: boolean;
}

export interface ServiceState {
  service_id: string;
  name: string;
  status: ServiceStatus;
  port: number;
  icon: string;
  description: string;
  healthy: boolean;
  pid: number | null;
  error: string | null;
  external: boolean;
  manageable: boolean;
}

export interface ServicesResponse {
  services: Record<string, ServiceState>;
  count: number;
}

export interface ServiceStatusUpdate {
  service_id: string;
  status: ServiceStatus;
  message: string;
}

export interface GpuInfo {
  name: string;
  total_mb: number;
  used_mb: number;
  free_mb: number;
  utilization: number;
}

export interface GpuProcess {
  pid: string;
  name: string;
  memory: string;
}

export interface OllamaModel {
  name: string;
  id: string;
  size: string;
  processor?: string;
}

export interface RunningServiceInfo {
  id: string;
  name: string;
  idle_seconds: number | null;
  gpu_intensive: boolean;
  start_time: number | null;
}

export interface ServiceSummary {
  total_running: number;
  gpu_intensive_running: number;
  running_services: RunningServiceInfo[];
  idle_services: RunningServiceInfo[];
  auto_stop_enabled: boolean;
  idle_timeout_seconds: number;
}

export interface ResourceSummary {
  gpu: GpuInfo | null;
  gpu_processes: GpuProcess[];
  ollama_models: OllamaModel[];
  services: ServiceSummary;
}

export interface ResourceSettings {
  auto_stop_enabled: boolean;
  idle_timeout_seconds: number;
  idle_timeout_minutes: number;
}
