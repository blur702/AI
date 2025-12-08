export type ServiceStatus = 'stopped' | 'starting' | 'running' | 'stopping' | 'error';

export interface ServiceConfig {
  id: string;
  name: string;
  port: number;
  icon: string;
  description: string;
  tags: string[];
  cardClass: string;
  section: 'main' | 'music' | 'image';
  external?: boolean;
  proxyId?: string;  // ID for reverse proxy path (e.g., 'n8n' -> /proxy/n8n/)
  instructions?: string;  // Setup instructions shown when service is running
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

// Ingestion Types

export interface CollectionStats {
  exists: boolean;
  object_count: number;
  entity_counts?: Record<string, number>;
}

export interface IngestionStatus {
  is_running: boolean;
  task_id: string | null;
  current_type: string | null;
  started_at: number | null;
  collections: {
    documentation: CollectionStats;
    code_entity: CollectionStats;
    drupal_api: CollectionStats;
  };
}

export interface IngestionProgress {
  task_id: string;
  type: 'documentation' | 'code' | 'drupal';
  phase: 'scanning' | 'processing' | 'indexing' | 'complete' | 'cancelled';
  current: number;
  total: number;
  message: string;
}

export interface IngestionPhaseComplete {
  task_id: string;
  type: 'documentation' | 'code' | 'drupal';
  stats: {
    files?: number;
    chunks?: number;
    entities?: number;
    entities_inserted?: number;
    entities_updated?: number;
    errors?: number;
  };
}

export interface IngestionComplete {
  task_id: string;
  success: boolean;
  stats: {
    documentation?: { files: number; chunks: number; errors: number };
    code?: { files: number; entities: number; errors: number };
    drupal?: { entities_inserted: number; entities_updated: number; errors: number };
  };
  duration_seconds: number;
}

export interface IngestionError {
  task_id: string;
  error: string;
  type: string | null;
}

export interface IngestionRequest {
  types: ('documentation' | 'code' | 'drupal')[];
  reindex: boolean;
  code_service?: string;
  drupal_limit?: number | null;
}

// Claude Code Execution Types

export type ClaudeSessionStatus = 'starting' | 'running' | 'completed' | 'cancelled' | 'error' | 'timeout';

export interface ClaudeSession {
  session_id: string;
  prompt: string;
  mode: 'normal' | 'yolo';
  status: ClaudeSessionStatus;
  start_time: number;
  end_time: number | null;
  output_lines: string[];
  error_message: string | null;
}

export interface ClaudeStatusUpdate {
  session_id: string;
  status: ClaudeSessionStatus;
  message: string;
  timestamp: number;
}

export interface ClaudeOutputLine {
  session_id: string;
  line: string;
  timestamp: number;
}

export interface ClaudeSessionList {
  sessions: ClaudeSession[];
}

export interface ClaudeExecuteRequest {
  prompt: string;
}

export interface ClaudeExecuteResponse {
  success: boolean;
  session_id?: string;
  message?: string;
  error?: string;
}
