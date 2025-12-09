import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { ServiceStatus, ServiceState, ServicesResponse, ServiceStatusUpdate, ModelDownloadProgress, ModelLoadProgress } from '../types';
import { getApiBase } from '../config/services';

export function useSocket() {
  const [connected, setConnected] = useState(false);
  const [services, setServices] = useState<Record<string, ServiceState>>({});
  const socketRef = useRef<Socket | null>(null);

  const fetchStatuses = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/services`, {
        credentials: 'include'
      });
      if (!response.ok) {
        console.error(`Error fetching statuses: ${response.status} ${response.statusText}`);
        return;
      }
      const data: ServicesResponse = await response.json();
      if (data && data.services) {
        setServices(data.services);
      }
    } catch (error) {
      console.error('Error fetching statuses:', error);
    }
  }, []);

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

        socket.on('connect', () => {
          console.log('WebSocket connected');
          setConnected(true);
          // Fetch initial statuses when connected
          fetchStatuses();
        });

        socket.on('disconnect', () => {
          console.log('WebSocket disconnected');
          setConnected(false);
        });

        socket.on('service_status', (data: ServiceStatusUpdate) => {
          console.log('Service status update:', data);
          setServices(prev => ({
            ...prev,
            [data.service_id]: {
              ...prev[data.service_id],
              status: data.status,
              error: data.message || null
            }
          }));
        });

        // Model download progress events
        socket.on('model_download_progress', (data: ModelDownloadProgress) => {
          console.log('Model download progress:', data);
          // Notify the useModels hook via window callback
          const updateFn = (window as unknown as { __updateModelDownloadProgress?: (p: ModelDownloadProgress) => void }).__updateModelDownloadProgress;
          if (updateFn) {
            updateFn(data);
          }
        });

        // Model load/unload progress events
        socket.on('model_load_progress', (data: ModelLoadProgress) => {
          console.log('Model load progress:', data);
          // Notify the useModels hook via window callback
          const updateFn = (window as unknown as { __updateModelLoadProgress?: (p: ModelLoadProgress) => void }).__updateModelLoadProgress;
          if (updateFn) {
            updateFn(data);
          }
        });
      })
      .catch(error => {
        if (error.name === 'AbortError') return;
        console.error('Socket.IO authentication failed:', error);
        setConnected(false);
        // Still fetch statuses even if WebSocket fails - allows polling fallback
        fetchStatuses();
      });

    return () => {
      abortController.abort();
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, [fetchStatuses]);

  const startService = useCallback(async (serviceId: string) => {
    setServices(prev => ({
      ...prev,
      [serviceId]: {
        ...prev[serviceId],
        status: 'starting' as ServiceStatus,
        error: null
      }
    }));

    try {
      const response = await fetch(`${getApiBase()}/api/services/${serviceId}/start`, {
        method: 'POST',
        credentials: 'include'
      });
      const data = await response.json();

      if (!data.success) {
        setServices(prev => ({
          ...prev,
          [serviceId]: {
            ...prev[serviceId],
            status: 'error' as ServiceStatus,
            error: data.error || 'Failed to start'
          }
        }));
      }
    } catch (error) {
      console.error('Error starting service:', error);
      setServices(prev => ({
        ...prev,
        [serviceId]: {
          ...prev[serviceId],
          status: 'error' as ServiceStatus,
          error: 'Connection error'
        }
      }));
    }
  }, []);

  const stopService = useCallback(async (serviceId: string) => {
    setServices(prev => ({
      ...prev,
      [serviceId]: {
        ...prev[serviceId],
        status: 'stopping' as ServiceStatus,
        error: null
      }
    }));

    try {
      const response = await fetch(`${getApiBase()}/api/services/${serviceId}/stop`, {
        method: 'POST',
        credentials: 'include'
      });
      const data = await response.json();

      if (data.success) {
        setServices(prev => ({
          ...prev,
          [serviceId]: {
            ...prev[serviceId],
            status: 'stopped' as ServiceStatus
          }
        }));
      } else {
        setServices(prev => ({
          ...prev,
          [serviceId]: {
            ...prev[serviceId],
            status: 'error' as ServiceStatus,
            error: data.error || 'Failed to stop'
          }
        }));
      }
    } catch (error) {
      console.error('Error stopping service:', error);
      setServices(prev => ({
        ...prev,
        [serviceId]: {
          ...prev[serviceId],
          status: 'error' as ServiceStatus,
          error: 'Connection error'
        }
      }));
    }
  }, []);

  return {
    connected,
    services,
    startService,
    stopService,
    refreshStatuses: fetchStatuses
  };
}
