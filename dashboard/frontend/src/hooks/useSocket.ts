import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { ServiceStatus, ServiceState, ServicesResponse, ServiceStatusUpdate } from '../types';
import { getApiBase } from '../config/services';

export function useSocket() {
  const [connected, setConnected] = useState(false);
  const [services, setServices] = useState<Record<string, ServiceState>>({});
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    const socket = io(getApiBase(), {
      transports: ['websocket', 'polling']
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('WebSocket connected');
      setConnected(true);
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

    // Fetch initial statuses
    fetchStatuses();

    return () => {
      socket.disconnect();
    };
  }, []);

  const fetchStatuses = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/services`);
      const data: ServicesResponse = await response.json();
      setServices(data.services);
    } catch (error) {
      console.error('Error fetching statuses:', error);
    }
  }, []);

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
        method: 'POST'
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
        method: 'POST'
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
