export type ServiceStatus =
  | "stopped"
  | "starting"
  | "running"
  | "paused"
  | "stopping"
  | "error";

export interface ServiceConfig {
  id: string;
  name: string;
  port: number;
  icon: string;
  description: string;
  tags: string[];
  cardClass: string;
  section: "main" | "music" | "image";
  external?: boolean;
  proxyId?: string; // ID for reverse proxy path (e.g., 'n8n' -> /proxy/n8n/)
  instructions?: string; // Setup instructions shown when service is running
  models?: string[]; // Model names this service uses ('*' for any Ollama model)
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

export interface OllamaModelDetailed extends OllamaModel {
  family: string;
  parameters: string; // e.g., "32B"
  quantization: string; // e.g., "Q4_K_M"
  size_gb: number;
  format: string;
  template?: string;
  estimated_vram_mb: number;
  capability_description: string;
  is_loaded: boolean;
  detailed?: boolean; // Whether full details were fetched
}

export interface ModelDownloadProgress {
  model_name: string;
  progress: string;
  status: "downloading" | "complete" | "error";
}

export interface ModelLoadProgress {
  model_name: string;
  progress: number; // 0-100 percentage
  status: "loading" | "unloading" | "complete" | "error";
  action: "load" | "unload";
  message?: string;
}

export interface ModelServiceInfo {
  id: string;
  name: string;
  status: string;
}

export interface ModelsListResponse {
  models: OllamaModel[];
  count: number;
}

export interface ModelsDetailedResponse {
  models: OllamaModelDetailed[];
  count: number;
  loaded_count: number;
}

export interface ModelInfoResponse extends OllamaModelDetailed {}

export interface ModelActionResponse {
  success: boolean;
  message: string;
  model_name: string;
  error?: {
    code: string;
    details: string;
  };
}

export interface ModelServicesResponse {
  model_name: string;
  services: ModelServiceInfo[];
  count: number;
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
  paused: boolean;
  task_id: string | null;
  current_type: string | null;
  started_at: number | null;
  collections: {
    documentation: CollectionStats;
    code_entity: CollectionStats;
    drupal_api: CollectionStats;
    mdn_javascript: CollectionStats;
    mdn_webapis: CollectionStats;
  };
}

export interface IngestionProgress {
  task_id: string;
  type: "documentation" | "code" | "drupal" | "mdn_javascript" | "mdn_webapis";
  phase: "scanning" | "processing" | "indexing" | "complete" | "cancelled";
  current: number;
  total: number;
  message: string;
  paused: boolean;
}

export interface IngestionPhaseComplete {
  task_id: string;
  type: "documentation" | "code" | "drupal" | "mdn_javascript" | "mdn_webapis";
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
    drupal?: {
      entities_inserted: number;
      entities_updated: number;
      errors: number;
    };
    mdn_javascript?: {
      entities_inserted: number;
      entities_updated: number;
      errors: number;
    };
    mdn_webapis?: {
      entities_inserted: number;
      entities_updated: number;
      errors: number;
    };
  };
  duration_seconds: number;
}

export interface IngestionError {
  task_id: string;
  error: string;
  type: string | null;
}

export interface IngestionRequest {
  types: (
    | "documentation"
    | "code"
    | "drupal"
    | "mdn_javascript"
    | "mdn_webapis"
  )[];
  reindex: boolean;
  code_service?: string;
  drupal_limit?: number | null;
  mdn_limit?: number | null;
  mdn_section?: string | null; // For mdn_webapis: 'css', 'html', or 'webapi'
}

// Claude Code Execution Types

export type ClaudeSessionStatus =
  | "starting"
  | "running"
  | "completed"
  | "cancelled"
  | "error"
  | "timeout";

export interface ClaudeSession {
  session_id: string;
  prompt: string;
  mode: "normal" | "yolo";
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

export interface HealthStatus {
  status: "healthy" | "warning" | "error";
  uptime_seconds: number;
  cpu: {
    percent: number;
    count: number;
  };
  memory: {
    percent: number;
    used_mb: number;
    total_mb: number;
  };
  services: {
    total: number;
    running: number;
  };
}

// Pause/Resume Event Types

export interface IngestionPaused {
  task_id: string;
  timestamp: number;
}

export interface IngestionResumed {
  task_id: string;
  timestamp: number;
}

export interface ServicePaused {
  service_id: string;
  status: "paused";
  message: string;
}

export interface ServiceResumed {
  service_id: string;
  status: "running";
  message: string;
}

export interface CleanCollectionsRequest {
  collections: (
    | "documentation"
    | "code_entity"
    | "drupal_api"
    | "mdn_javascript"
    | "mdn_webapis"
  )[];
}

export interface CleanCollectionsResponse {
  success: boolean;
  deleted: string[];
  errors: string[] | null;
}

// Re-export Congressional types
export type {
  CongressionalStatus,
  CongressionalProgress,
  CongressionalChatMessage,
  CongressionalQueryRequest,
  CongressionalQueryResult,
  CongressionalQueryResponse,
  CongressionalScrapeConfig,
  MemberStats,
  CongressionalChatRequest,
  CongressionalChatSource,
  CongressionalChatResponse,
  ChatHistoryItem,
} from "./congressional";

// Re-export Price Comparison types
export type {
  ProductAttributes,
  Product,
  ProductGroup,
  ComparisonResult,
  SearchProgress,
  SavedSelection,
  ShoppingListItem,
  BulkUploadResult,
  ShoppingListItemResult,
  ShoppingListStats,
  ProductSearchRequest,
  BulkUploadRequest,
  GroceryService,
} from "./priceComparison";

export {
  GROCERY_SERVICES,
  getServiceColor,
  getServiceName,
} from "./priceComparison";
