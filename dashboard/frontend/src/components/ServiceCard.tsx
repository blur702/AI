import { ServiceConfig, ServiceState, ServiceStatus } from '../types';
import { getServiceUrl } from '../config/services';
import './ServiceCard.css';

interface ServiceCardProps {
  config: ServiceConfig;
  state?: ServiceState;
  onStart: (id: string) => void;
  onStop: (id: string) => void;
}

export function ServiceCard({ config, state, onStart, onStop }: ServiceCardProps) {
  const status: ServiceStatus = state?.status || 'stopped';
  const isRunning = status === 'running';
  const isStarting = status === 'starting';
  const isStopping = status === 'stopping';
  const isError = status === 'error';
  const isExternal = config.external;
  const canManage = !isExternal && state?.manageable !== false;

  const handleOpen = () => {
    if (isRunning) {
      window.open(getServiceUrl(config.port, config.proxyId), '_blank');
    }
  };

  const getStatusClass = () => {
    switch (status) {
      case 'running': return 'status-running';
      case 'starting': return 'status-starting';
      case 'stopping': return 'status-starting';
      case 'error': return 'status-stopped';
      default: return 'status-stopped';
    }
  };

  const getIndicatorClass = () => {
    switch (status) {
      case 'running': return 'status-online';
      case 'starting': return 'status-starting-indicator';
      case 'stopping': return 'status-starting-indicator';
      default: return 'status-offline';
    }
  };

  return (
    <div className={`card ${config.cardClass} ${getStatusClass()}`}>
      <div className="card-header">
        <div className="card-icon">{config.icon}</div>
        <div>
          <div className="card-title">{config.name}</div>
          <div className="card-port">
            <span className={`status ${getIndicatorClass()}`}></span>
            Port {config.port}
          </div>
        </div>
      </div>

      <p className="card-description">{config.description}</p>

      <div className="card-features">
        {config.tags.map(tag => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>

      <div className="card-actions">
        {canManage && (
          <>
            {!isRunning && !isStopping && (
              <button
                className="btn btn-start"
                onClick={() => onStart(config.id)}
                disabled={isStarting}
              >
                {isStarting ? 'Starting...' : 'Start'}
              </button>
            )}
            {(isRunning || isStopping) && (
              <button
                className="btn btn-stop"
                onClick={() => onStop(config.id)}
                disabled={isStopping}
              >
                {isStopping ? 'Stopping...' : 'Stop'}
              </button>
            )}
          </>
        )}
        <button
          className="btn btn-open"
          onClick={handleOpen}
          disabled={!isRunning}
        >
          Open
        </button>
      </div>

      {(isStarting || isStopping || isError) && (
        <div className="status-message visible">
          {!isError && <div className="spinner"></div>}
          <div className="status-text">
            {isStarting && 'Starting service...'}
            {isStopping && 'Stopping service...'}
            {isError && (state?.error || 'Error')}
          </div>
        </div>
      )}
    </div>
  );
}
