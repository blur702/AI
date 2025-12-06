import { ServiceCard } from './components/ServiceCard';
import { ConnectionStatus } from './components/ConnectionStatus';
import { useSocket } from './hooks/useSocket';
import { SERVICES_CONFIG } from './config/services';
import './App.css';

function App() {
  const { connected, services, startService, stopService } = useSocket();

  const mainServices = SERVICES_CONFIG.filter(s => s.section === 'main');
  const musicServices = SERVICES_CONFIG.filter(s => s.section === 'music');

  const serverIp = window.location.hostname || '10.0.0.138';

  return (
    <div className="container">
      <h1>AI Services Dashboard</h1>
      <p className="subtitle">Local AI Infrastructure - On-Demand Services</p>

      <div className="ip-info">
        Server IP: <span>{serverIp}</span>
      </div>

      <div className="grid">
        {mainServices.map(config => (
          <ServiceCard
            key={config.id}
            config={config}
            state={services[config.id]}
            onStart={startService}
            onStop={stopService}
          />
        ))}
      </div>

      <h2 className="section-title">Music Generation</h2>
      <div className="grid">
        {musicServices.map(config => (
          <ServiceCard
            key={config.id}
            config={config}
            state={services[config.id]}
            onStart={startService}
            onStop={stopService}
          />
        ))}
      </div>

      <div className="footer">
        <p>RTX 3090 (24GB) - Ryzen 9 5900X - 64GB RAM</p>
      </div>

      <ConnectionStatus connected={connected} />
    </div>
  );
}

export default App;
