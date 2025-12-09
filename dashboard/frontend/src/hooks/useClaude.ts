import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import {
  ClaudeSession,
  ClaudeStatusUpdate,
  ClaudeOutputLine,
  ClaudeExecuteResponse,
} from '../types';
import { getApiBase } from '../config/services';

export function useClaude() {
  const [sessions, setSessions] = useState<ClaudeSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [outputLines, setOutputLines] = useState<Map<string, string[]>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const socketRef = useRef<Socket | null>(null);

  // Fetch sessions list
  const fetchSessions = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/claude/sessions`, {
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setSessions(data.sessions || []);
      setError(null);
    } catch (err) {
      console.error('Error fetching Claude sessions:', err);
      setError('Failed to fetch sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch session with output
  const fetchSessionOutput = useCallback(async (sessionId: string) => {
    try {
      const response = await fetch(`${getApiBase()}/api/claude/sessions/${sessionId}?include_output=true`, {
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: ClaudeSession = await response.json();
      if (data.output_lines) {
        setOutputLines(prev => {
          const next = new Map(prev);
          next.set(sessionId, data.output_lines || []);
          return next;
        });
      }
      return data;
    } catch (err) {
      console.error('Error fetching session output:', err);
      return null;
    }
  }, []);

  // Set up WebSocket listeners
  useEffect(() => {
    const abortController = new AbortController();

    // Fetch session token for Socket.IO authentication
    fetch(`${getApiBase()}/api/auth/token`, {
      credentials: 'include',
      signal: abortController.signal,
    })
      .then(res => {
        if (abortController.signal.aborted) return;
        if (!res.ok) throw new Error('Authentication required');
        return res.json();
      })
      .then(data => {
        if (abortController.signal.aborted || !data) return;
        // Connect with token in auth payload
        const socket = io(getApiBase(), {
          transports: ['websocket', 'polling'],
          auth: {
            token: data.token
          }
        });
        socketRef.current = socket;

        // Listen for status updates
        socket.on('claude_status', (data: ClaudeStatusUpdate) => {
          console.log('Claude status:', data);
          // Update session in list
          setSessions(prev => {
            const idx = prev.findIndex(s => s.session_id === data.session_id);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = { ...updated[idx], status: data.status };
              return updated;
            }
            return prev;
          });
        });

        // Listen for output lines
        socket.on('claude_output', (data: ClaudeOutputLine) => {
          setOutputLines(prev => {
            const next = new Map(prev);
            const lines = next.get(data.session_id) || [];
            next.set(data.session_id, [...lines, data.line]);
            return next;
          });
        });

        // Listen for session list updates
        socket.on('claude_session_list', (data: { sessions: ClaudeSession[] }) => {
          console.log('Claude session list updated:', data);
          setSessions(data.sessions);
        });

        // Fetch initial sessions
        fetchSessions();
      })
      .catch(error => {
        if (error.name === 'AbortError') return;
        console.error('Socket.IO authentication failed:', error);
        setError('Authentication failed');
        setLoading(false);
      });

    return () => {
      abortController.abort();
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, [fetchSessions]);

  // Execute Claude in normal mode
  const executeNormal = useCallback(async (prompt: string): Promise<ClaudeExecuteResponse> => {
    setError(null);

    try {
      const response = await fetch(`${getApiBase()}/api/claude/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ prompt }),
      });

      const data: ClaudeExecuteResponse = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to execute');
        return data;
      }

      // Set as active session and initialize output buffer
      if (data.session_id) {
        setActiveSessionId(data.session_id);
        setOutputLines(prev => {
          const next = new Map(prev);
          next.set(data.session_id!, []);
          return next;
        });
      }

      return data;
    } catch (err) {
      console.error('Error executing Claude:', err);
      const errorResponse: ClaudeExecuteResponse = {
        success: false,
        error: 'Connection error',
      };
      setError('Connection error');
      return errorResponse;
    }
  }, []);

  // Execute Claude in YOLO mode
  const executeYolo = useCallback(async (prompt: string): Promise<ClaudeExecuteResponse> => {
    setError(null);

    try {
      const response = await fetch(`${getApiBase()}/api/claude/execute-yolo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ prompt }),
      });

      const data: ClaudeExecuteResponse = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to execute');
        return data;
      }

      // Set as active session and initialize output buffer
      if (data.session_id) {
        setActiveSessionId(data.session_id);
        setOutputLines(prev => {
          const next = new Map(prev);
          next.set(data.session_id!, []);
          return next;
        });
      }

      return data;
    } catch (err) {
      console.error('Error executing Claude (YOLO):', err);
      const errorResponse: ClaudeExecuteResponse = {
        success: false,
        error: 'Connection error',
      };
      setError('Connection error');
      return errorResponse;
    }
  }, []);

  // Cancel a session
  const cancelSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const response = await fetch(`${getApiBase()}/api/claude/sessions/${sessionId}/cancel`, {
        method: 'POST',
        credentials: 'include',
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to cancel');
        return false;
      }

      return true;
    } catch (err) {
      console.error('Error cancelling session:', err);
      setError('Connection error');
      return false;
    }
  }, []);

  // Get output for a session
  const getSessionOutput = useCallback((sessionId: string): string[] => {
    return outputLines.get(sessionId) || [];
  }, [outputLines]);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    sessions,
    activeSessionId,
    setActiveSessionId,
    outputLines,
    error,
    loading,
    executeNormal,
    executeYolo,
    cancelSession,
    getSessionOutput,
    fetchSessionOutput,
    fetchSessions,
    clearError,
  };
}
