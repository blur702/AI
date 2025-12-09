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

const MDN_SECTIONS = [
  { value: '', label: 'All sections' },
  { value: 'css', label: 'CSS only' },
  { value: 'html', label: 'HTML only' },
  { value: 'webapi', label: 'Web APIs only' },
];

type IngestionType = 'documentation' | 'code' | 'drupal' | 'mdn_javascript' | 'mdn_webapis';

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
  const [selectedTypes, setSelectedTypes] = useState<Set<IngestionType>>(
    new Set(['documentation', 'code'])
  );
  const [codeService, setCodeService] = useState('all');
  const [reindex, setReindex] = useState(false);
  const [drupalLimit, setDrupalLimit] = useState<number | null>(null);
  const [mdnLimit, setMdnLimit] = useState<number | null>(100);
  const [mdnSection, setMdnSection] = useState<string>('');

  const handleTypeToggle = useCallback((type: IngestionType) => {
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

    const hasMdn = selectedTypes.has('mdn_javascript') || selectedTypes.has('mdn_webapis');
    const request: IngestionRequest = {
      types: Array.from(selectedTypes),
      reindex,
      code_service: codeService,
      drupal_limit: selectedTypes.has('drupal') ? drupalLimit : undefined,
      mdn_limit: hasMdn ? mdnLimit : undefined,
      mdn_section: selectedTypes.has('mdn_webapis') && mdnSection ? mdnSection : undefined,
    };

    await startIngestion(request);
  }, [selectedTypes, reindex, codeService, drupalLimit, mdnLimit, mdnSection, startIngestion]);

  const handleCancel = useCallback(async () => {
    await cancelIngestion();
  }, [cancelIngestion]);

  if (loading) {
    return <div className="settings-panel loading">Loading settings...</div>;
  }

  const isRunning = status?.is_running ?? false;
  const docCount = status?.collections?.documentation?.object_count ?? 0;
  const codeCount = status?.collections?.code_entity?.object_count ?? 0;
  const drupalCount = status?.collections?.drupal_api?.object_count ?? 0;
  const mdnJsCount = status?.collections?.mdn_javascript?.object_count ?? 0;
  const mdnWebCount = status?.collections?.mdn_webapis?.object_count ?? 0;

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
              <div className="stat-item">
                <span className="stat-label">Drupal API:</span>
                <span className="stat-value">{drupalCount.toLocaleString()} entities</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">MDN JavaScript:</span>
                <span className="stat-value">{mdnJsCount.toLocaleString()} docs</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">MDN Web APIs:</span>
                <span className="stat-value">{mdnWebCount.toLocaleString()} docs</span>
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
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedTypes.has('drupal')}
                  onChange={() => handleTypeToggle('drupal')}
                  disabled={isRunning}
                />
                Drupal API (Web Scrape)
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedTypes.has('mdn_javascript')}
                  onChange={() => handleTypeToggle('mdn_javascript')}
                  disabled={isRunning}
                />
                MDN JavaScript (Web Scrape)
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedTypes.has('mdn_webapis')}
                  onChange={() => handleTypeToggle('mdn_webapis')}
                  disabled={isRunning}
                />
                MDN Web APIs (CSS/HTML/WebAPI)
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

            {/* Drupal Limit Selector */}
            {selectedTypes.has('drupal') && (
              <div className="service-selector">
                <label htmlFor="drupal-limit-select">Drupal entity limit:</label>
                <select
                  id="drupal-limit-select"
                  value={drupalLimit ?? 'unlimited'}
                  onChange={(e) => setDrupalLimit(e.target.value === 'unlimited' ? null : parseInt(e.target.value))}
                  disabled={isRunning}
                >
                  <option value="unlimited">Unlimited (full scrape)</option>
                  <option value="100">100 entities</option>
                  <option value="500">500 entities</option>
                  <option value="1000">1,000 entities</option>
                  <option value="5000">5,000 entities</option>
                </select>
                <span className="help-text">Note: Full Drupal API scrape takes several hours</span>
              </div>
            )}

            {/* MDN Limit Selector */}
            {(selectedTypes.has('mdn_javascript') || selectedTypes.has('mdn_webapis')) && (
              <div className="service-selector">
                <label htmlFor="mdn-limit-select">MDN document limit:</label>
                <select
                  id="mdn-limit-select"
                  value={mdnLimit ?? 'unlimited'}
                  onChange={(e) => setMdnLimit(e.target.value === 'unlimited' ? null : parseInt(e.target.value))}
                  disabled={isRunning}
                >
                  <option value="50">50 documents</option>
                  <option value="100">100 documents</option>
                  <option value="250">250 documents</option>
                  <option value="500">500 documents</option>
                  <option value="unlimited">Unlimited (full scrape)</option>
                </select>
                <span className="help-text">Note: MDN scraping is rate-limited to respect their servers</span>
              </div>
            )}

            {/* MDN Section Filter (for Web APIs only) */}
            {selectedTypes.has('mdn_webapis') && (
              <div className="service-selector">
                <label htmlFor="mdn-section-select">MDN Web APIs section:</label>
                <select
                  id="mdn-section-select"
                  value={mdnSection}
                  onChange={(e) => setMdnSection(e.target.value)}
                  disabled={isRunning}
                >
                  {MDN_SECTIONS.map(({ value, label }) => (
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
                    {progress.type === 'documentation' ? 'Documentation' :
                     progress.type === 'code' ? 'Code' :
                     progress.type === 'drupal' ? 'Drupal API' :
                     progress.type === 'mdn_javascript' ? 'MDN JavaScript' :
                     progress.type === 'mdn_webapis' ? 'MDN Web APIs' : progress.type}
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
                  {lastResult.stats.drupal && (
                    <span>
                      Drupal: {lastResult.stats.drupal.entities_inserted} entities
                      {lastResult.stats.drupal.errors > 0 && (
                        <span className="error-count">
                          ({lastResult.stats.drupal.errors} errors)
                        </span>
                      )}
                    </span>
                  )}
                  {lastResult.stats.mdn_javascript && (
                    <span>
                      MDN JS: {lastResult.stats.mdn_javascript.entities_inserted} docs
                      {lastResult.stats.mdn_javascript.errors > 0 && (
                        <span className="error-count">
                          ({lastResult.stats.mdn_javascript.errors} errors)
                        </span>
                      )}
                    </span>
                  )}
                  {lastResult.stats.mdn_webapis && (
                    <span>
                      MDN Web: {lastResult.stats.mdn_webapis.entities_inserted} docs
                      {lastResult.stats.mdn_webapis.errors > 0 && (
                        <span className="error-count">
                          ({lastResult.stats.mdn_webapis.errors} errors)
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
