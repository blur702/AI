import { useCallback, useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import {
  CongressionalStatus,
  CongressionalProgress,
  CongressionalQueryRequest,
  CongressionalQueryResponse,
  CongressionalScrapeConfig,
  CongressionalChatRequest,
  CongressionalChatResponse,
} from '../types';
import { getApiBase } from '../config/services';

interface UseCongressionalReturn {
  status: CongressionalStatus | null;
  progress: CongressionalProgress | null;
  loading: boolean;
  error: string | null;
  startScrape: (config: CongressionalScrapeConfig) => Promise<boolean>;
  cancelScrape: () => Promise<boolean>;
  pauseScrape: () => Promise<boolean>;
  resumeScrape: () => Promise<boolean>;
  queryData: (request: CongressionalQueryRequest) => Promise<CongressionalQueryResponse | null>;
  askQuestion: (request: CongressionalChatRequest) => Promise<CongressionalChatResponse | null>;
  refreshStatus: () => Promise<void>;
}

export function useCongressional(): UseCongressionalReturn {
  const [status, setStatus] = useState<CongressionalStatus | null>(null);
  const [progress, setProgress] = useState<CongressionalProgress | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<Socket | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/status`, {
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: CongressionalStatus = await response.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      console.error('Error fetching congressional status:', err);
      setError('Failed to fetch congressional status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const abortController = new AbortController();

    fetch(`${getApiBase()}/api/auth/token`, {
      credentials: 'include',
      signal: abortController.signal,
    })
      .then((res) => {
        if (abortController.signal.aborted) return null;
        if (!res.ok) throw new Error('Authentication required');
        return res.json();
      })
      .then((data) => {
        if (!data || abortController.signal.aborted) return;

        const socket = io(getApiBase(), {
          transports: ['websocket', 'polling'],
          auth: { token: data.token },
        });
        socketRef.current = socket;

        socket.on('connect_error', (err) => {
          console.error('Socket.IO connection error (congressional):', err);
          setError(
            'Failed to establish real-time connection for congressional data. Please check your network and authentication.',
          );
          setLoading(false);
        });

        socket.on('disconnect', (reason) => {
          console.log('Socket.IO disconnected (congressional):', reason);
          if (reason !== 'io server disconnect' && reason !== 'io client disconnect') {
            setError('Real-time connection for congressional data lost. Updates may be delayed.');
          }
        });

        socket.on('connect', () => {
          console.log('Socket.IO connected for congressional data');
          setError((prev) => (prev && prev.includes('Real-time connection for congressional') ? null : prev));
        });

        socket.on('congressional_started', () => {
          setProgress(null);
          setError(null);
          fetchStatus();
        });

        socket.on('congressional_progress', (data: CongressionalProgress) => {
          setProgress(data);
        });

        socket.on('congressional_complete', () => {
          fetchStatus();
        });

        socket.on('congressional_error', (data: { error: string; stats?: unknown }) => {
          console.error('Congressional scraping error:', data);
          setError(data.error || 'Congressional scraping failed');
          fetchStatus();
        });

        socket.on('congressional_cancelled', () => {
          fetchStatus();
        });

        socket.on('congressional_paused', () => {
          fetchStatus();
        });

        socket.on('congressional_resumed', () => {
          fetchStatus();
        });

        fetchStatus();
      })
      .catch((err) => {
        if ((err as Error).name === 'AbortError') return;
        console.error('Socket.IO authentication failed (congressional):', err);
        setError('Authentication failed for congressional data. Please log in again.');
        setLoading(false);
        if (socketRef.current) {
          socketRef.current.disconnect();
          socketRef.current = null;
        }
      });

    return () => {
      abortController.abort();
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, [fetchStatus]);

  const startScrape = useCallback(async (config: CongressionalScrapeConfig) => {
    setError(null);
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/scrape/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(config),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to start congressional scraping');
        return false;
      }
      return true;
    } catch (err) {
      console.error('Error starting congressional scraping:', err);
      setError('Connection error while starting congressional scraping');
      return false;
    }
  }, []);

  const cancelScrape = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/scrape/cancel`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to cancel congressional scraping');
        return false;
      }
      return true;
    } catch (err) {
      console.error('Error cancelling congressional scraping:', err);
      setError('Connection error while cancelling congressional scraping');
      return false;
    }
  }, []);

  const pauseScrape = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/scrape/pause`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to pause congressional scraping');
        return false;
      }
      return true;
    } catch (err) {
      console.error('Error pausing congressional scraping:', err);
      setError('Connection error while pausing congressional scraping');
      return false;
    }
  }, []);

  const resumeScrape = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/scrape/resume`, {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to resume congressional scraping');
        return false;
      }
      return true;
    } catch (err) {
      console.error('Error resuming congressional scraping:', err);
      setError('Connection error while resuming congressional scraping');
      return false;
    }
  }, []);

  const queryData = useCallback(async (request: CongressionalQueryRequest) => {
    setError(null);
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(request),
      });
      const data: CongressionalQueryResponse = await response.json();
      if (!response.ok || !data.success) {
        // Log details for diagnostics
        console.error(
          'Congressional query failed',
          response.status,
          data,
        );
        const message =
          data?.error ||
          data?.message ||
          `Query failed (HTTP ${response.status})`;
        setError(message);
        return null;
      }
      return data;
    } catch (err) {
      console.error('Error querying congressional data:', err);
      setError('Connection error while querying congressional data');
      return null;
    }
  }, []);

  const askQuestion = useCallback(async (request: CongressionalChatRequest) => {
    setError(null);
    try {
      const response = await fetch(`${getApiBase()}/api/congressional/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(request),
      });
      const data: CongressionalChatResponse = await response.json();
      if (!response.ok || !data.success) {
        console.error('Congressional chat failed', response.status, data);
        const message =
          data?.error ||
          `Chat request failed (HTTP ${response.status})`;
        setError(message);
        return null;
      }
      return data;
    } catch (err) {
      console.error('Error in congressional chat:', err);
      setError('Connection error while processing your question');
      return null;
    }
  }, []);

  return {
    status,
    progress,
    loading,
    error,
    startScrape,
    cancelScrape,
    pauseScrape,
    resumeScrape,
    queryData,
    askQuestion,
    refreshStatus: fetchStatus,
  };
}
