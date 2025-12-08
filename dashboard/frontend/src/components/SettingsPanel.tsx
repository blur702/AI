import { useState, useCallback } from 'react';
import { useIngestion } from '../hooks/useIngestion';
import { IngestionRequest } from '../types';
import './SettingsPanel.css';

const CODE_SERVICES = [
  { value: 'all', label: 'All AI Services' },
  { value: 'core', label: 'Core Project' },
  { value: 'alltalk', label: 'AllTalk TTS' },
  { value: 'audiocraft', label: 'AudioCraft' },
  { value: 'comfyui', label: 'ComfyUI' },
  { value: 'diffrhythm', label: 'DiffRhythm' },
  { value: 'musicgpt', label: 'MusicGPT' },
  { value: 'stable_audio', label: 'Stable Audio' },
  { value: 'wan2gp', label: 'Wan2GP' },
  { value: 'yue', label: 'YuE' },
];

export function SettingsPanel() {
  const {
    status,
    progress,
    lastResult,
    error,
    loading,
    startIngestion,
    cancelIngestion,
  } = useIngestion();

  const [expanded, setExpanded] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<Set<'documentation' | 'code'>>(
    new Set(['documentation', 'code'])
  );
  const [codeService, setCodeService] = useState('all');
  const [reindex, setReindex] = useState(false);

  const handleTypeToggle = useCallback((type: 'documentation' | 'code') => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleStart = useCallback(async () => {
    if (selectedTypes.size === 0) return;

    const request: IngestionRequest = {
      types: Array.from(selectedTypes),
      reindex,
      code_service: codeService,
    };

    await startIngestion(request);
  }, [selectedTypes, reindex, codeService, startIngestion]);

  const handleCancel = useCallback(async () => {
    await cancelIngestion();
  }, [cancelIngestion]);

  if (loading) {
    return <div className="settings-panel loading">Loading settings...</div>;
  }

  const isRunning = status?.is_running ?? false;
  const docCount = status?.collections?.documentation?.object_count ?? 0;
  const codeCount = status?.collections?.code_entity?.object_count ?? 0;

  // Calculate progress percentage
  let progressPercent = 0;
  if (progress && progress.total > 0) {
    progressPercent = (progress.current / progress.total) * 100;
  }

  return (
    <div className={`settings-panel ${expanded ? 'expanded' : 'collapsed'}`}>
      <div className="settings-header" onClick={() => setExpanded(!expanded)}>
        <div className="settings-title">
          <span className="settings-icon">&#9881;</span>
          <span>Settings</span>
          {isRunning && <span className="running-badge">Indexing...</span>}
        </div>
        <span className="expand-icon">{expanded ? '-' : '+'}</span>
      </div>

      {expanded && (
        <div className="settings-content">
          {/* Weaviate Status */}
          <div className="settings-section">
            <h4>Weaviate Collections</h4>
            <div className="collection-stats">
              <div className="stat-item">
                <span className="stat-label">Documentation:</span>
                <span className="stat-value">{docCount.toLocaleString()} objects</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Code Entities:</span>
                <span className="stat-value">{codeCount.toLocaleString()} objects</span>
              </div>
            </div>
          </div>

          {/* Ingestion Controls */}
          <div className="settings-section">
            <h4>Reindex Database</h4>

            {/* Type Selection */}
            <div className="ingestion-options">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedTypes.has('documentation')}
                  onChange={() => handleTypeToggle('documentation')}
                  disabled={isRunning}
                />
                Documentation (Markdown)
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedTypes.has('code')}
                  onChange={() => handleTypeToggle('code')}
                  disabled={isRunning}
                />
                Code Entities
              </label>
            </div>

            {/* Code Service Selector */}
            {selectedTypes.has('code') && (
              <div className="service-selector">
                <label htmlFor="code-scope-select">Code scope:</label>
                <select
                  id="code-scope-select"
                  value={codeService}
                  onChange={(e) => setCodeService(e.target.value)}
                  disabled={isRunning}
                >
                  {CODE_SERVICES.map(({ value, label }) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Reindex Option */}
            <div className="reindex-option">
              <label className="checkbox-label warning">
                <input
                  type="checkbox"
                  checked={reindex}
                  onChange={(e) => setReindex(e.target.checked)}
                  disabled={isRunning}
                />
                Delete existing data before indexing
              </label>
            </div>

            {/* Action Buttons */}
            <div className="ingestion-actions">
              {!isRunning ? (
                <button
                  className="btn-start"
                  onClick={handleStart}
                  disabled={selectedTypes.size === 0}
                >
                  Start Indexing
                </button>
              ) : (
                <button className="btn-cancel" onClick={handleCancel}>
                  Cancel
                </button>
              )}
            </div>

            {/* Progress Display */}
            {isRunning && progress && (
              <div className="ingestion-progress">
                <div className="progress-header">
                  <span className="progress-type">
                    {progress.type === 'documentation' ? 'Documentation' : 'Code'}
                  </span>
                  <span className="progress-phase">{progress.phase}</span>
                </div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    data-width={progressPercent}
                  />
                </div>
                <div className="progress-details">
                  <span className="progress-count">
                    {progress.current} / {progress.total}
                  </span>
                  <span className="progress-message">{progress.message}</span>
                </div>
              </div>
            )}

            {/* Error Display */}
            {error && (
              <div className="ingestion-error">
                <strong>Error:</strong> {error}
              </div>
            )}

            {/* Result Display */}
            {lastResult && !isRunning && (
              <div className={`ingestion-result ${lastResult.success ? 'success' : 'failure'}`}>
                <div className="result-header">
                  {lastResult.success ? 'Indexing Complete' : 'Indexing Failed'}
                </div>
                <div className="result-details">
                  <span>Duration: {lastResult.duration_seconds.toFixed(1)}s</span>
                  {lastResult.stats.documentation && (
                    <span>
                      Docs: {lastResult.stats.documentation.chunks} chunks
                      {lastResult.stats.documentation.errors > 0 && (
                        <span className="error-count">
                          ({lastResult.stats.documentation.errors} errors)
                        </span>
                      )}
                    </span>
                  )}
                  {lastResult.stats.code && (
                    <span>
                      Code: {lastResult.stats.code.entities} entities
                      {lastResult.stats.code.errors > 0 && (
                        <span className="error-count">
                          ({lastResult.stats.code.errors} errors)
                        </span>
                      )}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
