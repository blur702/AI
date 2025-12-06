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
