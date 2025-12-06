import './ConnectionStatus.css';

interface ConnectionStatusProps {
  connected: boolean;
}

export function ConnectionStatus({ connected }: ConnectionStatusProps) {
  return (
    <div className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
      <span className={`status ${connected ? 'status-online' : 'status-offline'}`}></span>
      <span>{connected ? 'Connected' : 'Disconnected'}</span>
    </div>
  );
}
