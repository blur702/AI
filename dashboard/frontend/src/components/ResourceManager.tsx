import { useState, useEffect, useCallback } from 'react';
import { ResourceSummary, ResourceSettings, OllamaModel, GpuProcess } from '../types';
import { getApiBase } from '../config/services';
import './ResourceManager.css';

interface ResourceManagerProps {
  onUnloadModel?: (modelName: string) => void;
}

function formatBytes(mb: number): string {
  if (mb >= 1024) {
    return `${(mb / 1024).toFixed(1)} GB`;
  }
  return `${mb} MB`;
}

function formatIdleTime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return 'N/A';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

export function ResourceManager({ onUnloadModel }: ResourceManagerProps) {
  const [summary, setSummary] = useState<ResourceSummary | null>(null);
  const [settings, setSettings] = useState<ResourceSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, settingsRes] = await Promise.all([
        fetch(`${getApiBase()}/api/resources/summary`),
        fetch(`${getApiBase()}/api/resources/settings`)
      ]);

      if (!summaryRes.ok) {
        const errorText = await summaryRes.text();
        throw new Error(`Failed to fetch summary (${summaryRes.status}): ${errorText}`);
      }

      if (!settingsRes.ok) {
        const errorText = await settingsRes.text();
        throw new Error(`Failed to fetch settings (${settingsRes.status}): ${errorText}`);
      }

      const summaryData = await summaryRes.json();
      const settingsData = await settingsRes.json();

      setSummary(summaryData);
      setSettings(settingsData);
    } catch (error) {
      console.error('Error fetching resource data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleToggleAutoStop = async () => {
    if (!settings) return;

    try {
      const response = await fetch(`${getApiBase()}/api/resources/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_stop_enabled: !settings.auto_stop_enabled })
      });
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error('Error updating settings:', error);
    }
  };

  const handleTimeoutChange = async (minutes: number) => {
    try {
      const response = await fetch(`${getApiBase()}/api/resources/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idle_timeout_minutes: minutes })
      });
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error('Error updating settings:', error);
    }
  };

  const handleUnloadOllamaModel = async (modelName: string) => {
    try {
      await fetch(`${getApiBase()}/api/models/ollama/unload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName })
      });
      fetchData(); // Refresh
      onUnloadModel?.(modelName);
    } catch (error) {
      console.error('Error unloading model:', error);
    }
  };

  if (loading) {
    return <div className="resource-manager loading">Loading resource info...</div>;
  }

  // Normalize GPU info to a simple nullable value so TypeScript
  // doesn't have to deal with both `null` and `undefined`.
  const gpu = summary ? summary.gpu : null;
  const usedPercent = gpu ? (gpu.used_mb / gpu.total_mb) * 100 : 0;

  return (
    <div className={`resource-manager ${expanded ? 'expanded' : 'collapsed'}`}>
      <div className="resource-header" onClick={() => setExpanded(!expanded)}>
        <div className="resource-title">
          <span className="gpu-icon">GPU</span>
          {gpu && (
            <div className="vram-bar-mini">
              <div
                className={`vram-fill ${usedPercent > 80 ? 'high' : usedPercent > 50 ? 'medium' : 'low'}`}
                style={{ '--vram-width': `${usedPercent}%` } as React.CSSProperties}
              />
            </div>
          )}
          <span className="vram-text">
            {gpu ? `${formatBytes(gpu.used_mb)} / ${formatBytes(gpu.total_mb)}` : 'N/A'}
          </span>
        </div>
        <span className="expand-icon">{expanded ? '-' : '+'}</span>
      </div>

      {expanded && (
        <div className="resource-content">
          {/* GPU Info */}
          {gpu && (
            <div className="resource-section">
              <h4>GPU: {gpu.name}</h4>
              <div className="vram-bar">
                <div
                  className={`vram-fill ${usedPercent > 80 ? 'high' : usedPercent > 50 ? 'medium' : 'low'}`}
                  style={{ '--vram-width': `${usedPercent}%` } as React.CSSProperties}
                />
                <span className="vram-label">{usedPercent.toFixed(1)}%</span>
              </div>
              <div className="vram-stats">
                <span>Used: {formatBytes(gpu.used_mb)}</span>
                <span>Free: {formatBytes(gpu.free_mb)}</span>
                <span>Util: {gpu.utilization}%</span>
              </div>
            </div>
          )}

          {/* Loaded Ollama Models */}
          {summary?.ollama_models && summary.ollama_models.length > 0 && (
            <div className="resource-section">
              <h4>Loaded LLM Models</h4>
              <div className="model-list">
                {summary.ollama_models.map((model: OllamaModel) => (
                  <div key={model.name} className="model-item">
                    <span className="model-name">{model.name}</span>
                    <span className="model-size">{model.size}</span>
                    <button
                      className="btn-unload"
                      onClick={() => handleUnloadOllamaModel(model.name)}
                      title="Unload model"
                    >
                      X
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* GPU Processes */}
          {summary?.gpu_processes && summary.gpu_processes.length > 0 && (
            <div className="resource-section">
              <h4>GPU Processes</h4>
              <div className="process-list">
                {summary.gpu_processes.map((proc: GpuProcess) => (
                  <div key={proc.pid} className="process-item">
                    <span className="process-name">{proc.name.split('\\').pop()}</span>
                    <span className="process-memory">{proc.memory}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Running Services */}
          {summary?.services && summary.services.running_services.length > 0 && (
            <div className="resource-section">
              <h4>
                Running Services ({summary.services.total_running})
                {summary.services.gpu_intensive_running > 0 && (
                  <span className="gpu-badge">{summary.services.gpu_intensive_running} GPU</span>
                )}
              </h4>
              <div className="service-list">
                {summary.services.running_services.map(svc => (
                  <div key={svc.id} className={`service-item ${svc.gpu_intensive ? 'gpu' : ''}`}>
                    <span className="service-name">{svc.name}</span>
                    <span className="service-idle">
                      Idle: {formatIdleTime(svc.idle_seconds)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Auto-Stop Settings */}
          {settings && (
            <div className="resource-section settings">
              <h4>Auto-Stop Idle Services</h4>
              <div className="setting-row">
                <label>
                  <input
                    type="checkbox"
                    checked={settings.auto_stop_enabled}
                    onChange={handleToggleAutoStop}
                  />
                  Enable auto-stop for GPU services
                </label>
              </div>
              <div className="setting-row">
                <label>Timeout:</label>
                <select
                  value={settings.idle_timeout_minutes}
                  onChange={(e) => handleTimeoutChange(parseInt(e.target.value))}
                  disabled={!settings.auto_stop_enabled}
                  aria-label="Idle timeout duration"
                >
                  <option value={5}>5 minutes</option>
                  <option value={15}>15 minutes</option>
                  <option value={30}>30 minutes</option>
                  <option value={60}>1 hour</option>
                  <option value={120}>2 hours</option>
                </select>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
