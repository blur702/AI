import { useState, useCallback, useRef, useEffect } from 'react';
import { useClaude } from '../hooks/useClaude';
import { ClaudeSession } from '../types';
import './ClaudePanel.css';

export function ClaudePanel() {
  const {
    sessions,
    activeSessionId,
    setActiveSessionId,
    error,
    loading,
    executeNormal,
    executeYolo,
    cancelSession,
    getSessionOutput,
    fetchSessionOutput,
    clearError,
  } = useClaude();

  const [expanded, setExpanded] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [visibleSessionCount, setVisibleSessionCount] = useState(10);
  const outputRef = useRef<HTMLDivElement>(null);

  // Get current session output length for dependency tracking
  const currentOutputLength = getSessionOutput(activeSessionId || '').length;

  // Auto-scroll output to bottom when new content is added
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [activeSessionId, currentOutputLength]);

  // Load output when selecting a completed session
  useEffect(() => {
    if (activeSessionId) {
      const session = sessions.find(s => s.session_id === activeSessionId);
      if (session && session.status !== 'running' && session.status !== 'starting') {
        // Fetch full output for completed sessions
        if (currentOutputLength === 0 && session.output_lines.length > 0) {
          fetchSessionOutput(activeSessionId);
        }
      }
    }
  }, [activeSessionId, sessions, currentOutputLength, fetchSessionOutput]);

  const handleExecute = useCallback(async (mode: 'normal' | 'yolo') => {
    if (!prompt.trim() || isSubmitting) return;

    setIsSubmitting(true);
    clearError();

    const result = mode === 'normal'
      ? await executeNormal(prompt.trim())
      : await executeYolo(prompt.trim());

    if (result.success) {
      setPrompt(''); // Clear prompt on success
    }
    setIsSubmitting(false);
  }, [prompt, isSubmitting, executeNormal, executeYolo, clearError]);

  const handleCancel = useCallback(async () => {
    if (!activeSessionId) return;
    await cancelSession(activeSessionId);
  }, [activeSessionId, cancelSession]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Check Ctrl+Shift+Enter first (YOLO mode) - more specific condition
    if (e.ctrlKey && e.shiftKey && e.key === 'Enter') {
      e.preventDefault();
      handleExecute('yolo');
      return;
    }
    // Ctrl+Enter to execute in normal mode
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      handleExecute('normal');
    }
  }, [handleExecute]);

  const formatDuration = (startTime: number, endTime: number | null): string => {
    const end = endTime || Date.now() / 1000;
    const duration = end - startTime;
    if (duration < 60) return `${duration.toFixed(1)}s`;
    const minutes = Math.floor(duration / 60);
    const seconds = Math.floor(duration % 60);
    return `${minutes}m ${seconds}s`;
  };

  const formatTime = (timestamp: number): string => {
    return new Date(timestamp * 1000).toLocaleTimeString();
  };

  const getStatusClass = (status: string): string => {
    switch (status) {
      case 'running':
      case 'starting':
        return 'status-running';
      case 'completed':
        return 'status-completed';
      case 'error':
      case 'timeout':
        return 'status-error';
      case 'cancelled':
        return 'status-cancelled';
      default:
        return '';
    }
  };

  const getStatusIcon = (status: string): string => {
    switch (status) {
      case 'running':
      case 'starting':
        return '\u25B6'; // Play
      case 'completed':
        return '\u2714'; // Check
      case 'error':
      case 'timeout':
        return '\u2716'; // X
      case 'cancelled':
        return '\u25A0'; // Stop
      default:
        return '\u25CF'; // Circle
    }
  };

  const activeSession = activeSessionId
    ? sessions.find(s => s.session_id === activeSessionId)
    : null;

  const currentOutput = activeSessionId ? getSessionOutput(activeSessionId) : [];
  const isRunning = activeSession?.status === 'running' || activeSession?.status === 'starting';

  // Count running sessions
  const runningCount = sessions.filter(s => s.status === 'running' || s.status === 'starting').length;

  if (loading) {
    return <div className="claude-panel loading">Loading Claude CLI...</div>;
  }

  return (
    <div className={`claude-panel ${expanded ? 'expanded' : 'collapsed'}`}>
      <div className="claude-header" onClick={() => setExpanded(!expanded)}>
        <div className="claude-title">
          <span className="claude-icon">&gt;_</span>
          <span>Claude Code CLI</span>
          {runningCount > 0 && (
            <span className="running-badge">{runningCount} running</span>
          )}
        </div>
        <span className="expand-icon">{expanded ? '-' : '+'}</span>
      </div>

      {expanded && (
        <div className="claude-content">
          {/* Prompt Input Section */}
          <div className="claude-section">
            <h4>Execute Command</h4>
            <div className="prompt-container">
              <textarea
                className="prompt-input"
                placeholder="Enter your prompt for Claude Code..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isSubmitting}
                rows={4}
              />
              <div className="prompt-actions">
                <button
                  className="btn-execute"
                  onClick={() => handleExecute('normal')}
                  disabled={!prompt.trim() || isSubmitting}
                  title="Execute (Ctrl+Enter)"
                >
                  {isSubmitting ? 'Starting...' : 'Execute'}
                </button>
                <button
                  className="btn-execute-yolo"
                  onClick={() => handleExecute('yolo')}
                  disabled={!prompt.trim() || isSubmitting}
                  title="Execute without permission prompts (Ctrl+Shift+Enter)"
                >
                  {isSubmitting ? 'Starting...' : 'YOLO Mode'}
                </button>
              </div>
              <div className="prompt-hints">
                <span>Ctrl+Enter: Execute</span>
                <span>Ctrl+Shift+Enter: YOLO Mode</span>
              </div>
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <div className="claude-error">
              <strong>Error:</strong> {error}
              <button className="btn-dismiss" onClick={clearError}>&times;</button>
            </div>
          )}

          {/* Sessions List */}
          <div className="claude-section">
            <h4>Sessions {sessions.length > 0 && `(${sessions.length})`}</h4>
            <div className="sessions-list">
              {sessions.length === 0 ? (
                <div className="no-sessions">No sessions yet</div>
              ) : (
                <>
                  {sessions.slice(0, visibleSessionCount).map((session: ClaudeSession) => (
                    <div
                      key={session.session_id}
                      className={`session-item ${activeSessionId === session.session_id ? 'active' : ''} ${getStatusClass(session.status)}`}
                      onClick={() => setActiveSessionId(session.session_id)}
                    >
                      <div className="session-header">
                        <span className="session-status-icon">{getStatusIcon(session.status)}</span>
                        <span className="session-prompt" title={session.prompt}>
                          {session.prompt.length > 50 ? session.prompt.substring(0, 50) + '...' : session.prompt}
                        </span>
                        <span className={`session-mode ${session.mode}`}>{session.mode}</span>
                      </div>
                      <div className="session-meta">
                        <span className="session-time">{formatTime(session.start_time)}</span>
                        <span className="session-duration">
                          {formatDuration(session.start_time, session.end_time)}
                        </span>
                        <span className={`session-status ${getStatusClass(session.status)}`}>
                          {session.status}
                        </span>
                      </div>
                    </div>
                  ))}
                  {sessions.length > visibleSessionCount && (
                    <button
                      className="btn-show-more"
                      onClick={() => setVisibleSessionCount(sessions.length)}
                      aria-label={`Show ${sessions.length - visibleSessionCount} more sessions`}
                    >
                      Show all ({sessions.length - visibleSessionCount} more)
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Output Terminal */}
          {activeSession && (
            <div className="claude-section terminal-section">
              <div className="terminal-header">
                <h4>Output</h4>
                {isRunning && (
                  <button className="btn-cancel" onClick={handleCancel}>
                    Cancel
                  </button>
                )}
              </div>
              <div className="terminal-container" ref={outputRef}>
                <div className="terminal-prompt-display">
                  <span className="terminal-prompt-label">$</span>
                  <span className="terminal-prompt-text">{activeSession.prompt}</span>
                </div>
                {currentOutput.length === 0 && isRunning && (
                  <div className="terminal-waiting">Waiting for output...</div>
                )}
                {currentOutput.map((line, idx) => (
                  <div key={idx} className="terminal-line">
                    {line}
                  </div>
                ))}
                {activeSession.error_message && (
                  <div className="terminal-error">
                    Error: {activeSession.error_message}
                  </div>
                )}
                {isRunning && (
                  <div className="terminal-cursor">
                    <span className="cursor-blink">_</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
