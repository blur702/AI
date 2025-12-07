import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import {
  IngestionStatus,
  IngestionProgress,
  IngestionComplete,
  IngestionError,
  IngestionRequest,
} from '../types';
import { getApiBase } from '../config/services';

export function useIngestion() {
  const [status, setStatus] = useState<IngestionStatus | null>(null);
  const [progress, setProgress] = useState<IngestionProgress | null>(null);
  const [lastResult, setLastResult] = useState<IngestionComplete | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const socketRef = useRef<Socket | null>(null);

  // Fetch initial status
  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/status`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: IngestionStatus = await response.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      console.error('Error fetching ingestion status:', err);
      setError('Failed to fetch ingestion status');
    } finally {
      setLoading(false);
    }
  }, []);

  // Set up WebSocket listeners
  useEffect(() => {
    const socket = io(getApiBase(), {
      transports: ['websocket', 'polling'],
    });
    socketRef.current = socket;

    socket.on('ingestion_started', (data: { task_id: string; types: string[]; reindex: boolean }) => {
      console.log('Ingestion started:', data);
      setProgress(null);
      setLastResult(null);
      setError(null);
      // Refresh status
      fetchStatus();
    });

    socket.on('ingestion_progress', (data: IngestionProgress) => {
      console.log('Ingestion progress:', data);
      setProgress(data);
    });

    socket.on('ingestion_phase_complete', (data: { task_id: string; type: string; stats: object }) => {
      console.log('Ingestion phase complete:', data);
    });

    socket.on('ingestion_complete', (data: IngestionComplete) => {
      console.log('Ingestion complete:', data);
      setLastResult(data);
      setProgress(null);
      // Refresh status to get updated collection counts
      fetchStatus();
    });

    socket.on('ingestion_cancelled', (data: { task_id: string }) => {
      console.log('Ingestion cancelled:', data);
      setProgress(null);
      fetchStatus();
    });

    socket.on('ingestion_error', (data: IngestionError) => {
      console.error('Ingestion error:', data);
      setError(data.error);
      setProgress(null);
      fetchStatus();
    });

    // Fetch initial status
    fetchStatus();

    return () => {
      socket.disconnect();
    };
  }, [fetchStatus]);

  // Start ingestion
  const startIngestion = useCallback(async (request: IngestionRequest) => {
    setError(null);
    setLastResult(null);

    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to start ingestion');
        return false;
      }

      return true;
    } catch (err) {
      console.error('Error starting ingestion:', err);
      setError('Connection error');
      return false;
    }
  }, []);

  // Cancel ingestion
  const cancelIngestion = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/cancel`, {
        method: 'POST',
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || 'Failed to cancel ingestion');
        return false;
      }

      return true;
    } catch (err) {
      console.error('Error cancelling ingestion:', err);
      setError('Connection error');
      return false;
    }
  }, []);

  return {
    status,
    progress,
    lastResult,
    error,
    loading,
    startIngestion,
    cancelIngestion,
    refreshStatus: fetchStatus,
  };
}
