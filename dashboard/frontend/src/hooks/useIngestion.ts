import { useEffect, useState, useCallback, useRef } from "react";
import { io, Socket } from "socket.io-client";
import {
  IngestionStatus,
  IngestionProgress,
  IngestionComplete,
  IngestionError,
  IngestionRequest,
  IngestionPaused,
  IngestionResumed,
  CleanCollectionsRequest,
} from "../types";
import { getApiBase } from "../config/services";

interface UseIngestionReturn {
  status: IngestionStatus | null;
  progress: IngestionProgress | null;
  lastResult: IngestionComplete | null;
  error: string | null;
  loading: boolean;
  startIngestion: (request: IngestionRequest) => Promise<boolean>;
  cancelIngestion: () => Promise<boolean>;
  pauseIngestion: () => Promise<boolean>;
  resumeIngestion: () => Promise<boolean>;
  cleanCollections: (request: CleanCollectionsRequest) => Promise<boolean>;
  reindexCollections: (request: IngestionRequest) => Promise<boolean>;
  refreshStatus: () => Promise<void>;
}

export function useIngestion(): UseIngestionReturn {
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
      console.error("Error fetching ingestion status:", err);
      setError("Failed to fetch ingestion status");
    } finally {
      setLoading(false);
    }
  }, []);

  // Set up WebSocket listeners
  useEffect(() => {
    const abortController = new AbortController();

    // Fetch session token for Socket.IO authentication
    fetch(`${getApiBase()}/api/auth/token`, {
      credentials: "include",
      signal: abortController.signal,
    })
      .then((res) => {
        if (abortController.signal.aborted) return;
        if (!res.ok) throw new Error("Authentication required");
        return res.json();
      })
      .then((data) => {
        if (abortController.signal.aborted || !data) return;
        // Connect with token in auth payload
        const socket = io(getApiBase(), {
          transports: ["websocket", "polling"],
          auth: {
            token: data.token,
          },
        });
        socketRef.current = socket;

        // Connection error handler
        socket.on("connect_error", (err) => {
          console.error("Socket.IO connection error:", err);
          setError(
            "Failed to establish real-time connection. Please check your network and authentication.",
          );
          setLoading(false);
        });

        // Disconnect handler
        socket.on("disconnect", (reason) => {
          console.log("Socket.IO disconnected:", reason);

          // Differentiate between intentional and unexpected disconnects
          if (
            reason === "io server disconnect" ||
            reason === "io client disconnect"
          ) {
            // Intentional disconnect (server closed connection or client called disconnect())
            console.log("Intentional disconnect, no action needed");
          } else {
            // Unexpected disconnect (network error, timeout, etc.)
            console.warn("Unexpected disconnect:", reason);
            setError(
              "Real-time connection lost. Updates may be delayed. Attempting to reconnect...",
            );
          }
        });

        // Connection established
        socket.on("connect", () => {
          console.log("Socket.IO connected for ingestion");
          // Clear any previous connection errors using functional state update
          setError((prev) => {
            if (prev && prev.includes("real-time connection")) {
              return null;
            }
            return prev;
          });
        });

        socket.on(
          "ingestion_started",
          (data: { task_id: string; types: string[]; reindex: boolean }) => {
            console.log("Ingestion started:", data);
            setProgress(null);
            setLastResult(null);
            setError(null);
            // Refresh status
            fetchStatus();
          },
        );

        socket.on("ingestion_progress", (data: IngestionProgress) => {
          console.log("Ingestion progress:", data);
          setProgress(data);
        });

        socket.on(
          "ingestion_phase_complete",
          (data: { task_id: string; type: string; stats: object }) => {
            console.log("Ingestion phase complete:", data);
          },
        );

        socket.on("ingestion_complete", (data: IngestionComplete) => {
          console.log("Ingestion complete:", data);
          setLastResult(data);
          setProgress(null);
          // Refresh status to get updated collection counts
          fetchStatus();
        });

        socket.on("ingestion_cancelled", (data: { task_id: string }) => {
          console.log("Ingestion cancelled:", data);
          setProgress(null);
          fetchStatus();
        });

        socket.on("ingestion_error", (data: IngestionError) => {
          console.error("Ingestion error:", data);
          setError(data.error);
          setProgress(null);
          fetchStatus();
        });

        socket.on("ingestion_paused", (data: IngestionPaused) => {
          console.log("Ingestion paused:", data);
          setStatus((prev) => (prev ? { ...prev, paused: true } : prev));
        });

        socket.on("ingestion_resumed", (data: IngestionResumed) => {
          console.log("Ingestion resumed:", data);
          setStatus((prev) => (prev ? { ...prev, paused: false } : prev));
        });

        // Fetch initial status
        fetchStatus();
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        console.error("Socket.IO authentication failed:", err);
        // Update state to reflect authentication failure
        setError(
          "Authentication failed. Please log in again to enable real-time updates.",
        );
        setLoading(false);
        // Clean up socket reference to avoid leftover connections
        if (socketRef.current) {
          socketRef.current.disconnect();
          socketRef.current = null;
        }
      });

    return () => {
      abortController.abort();
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, [fetchStatus]);

  // Start ingestion
  const startIngestion = useCallback(async (request: IngestionRequest) => {
    setError(null);
    setLastResult(null);

    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || "Failed to start ingestion");
        return false;
      }

      return true;
    } catch (err) {
      console.error("Error starting ingestion:", err);
      setError("Connection error");
      return false;
    }
  }, []);

  // Cancel ingestion
  const cancelIngestion = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/cancel`, {
        method: "POST",
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || "Failed to cancel ingestion");
        return false;
      }

      return true;
    } catch (err) {
      console.error("Error cancelling ingestion:", err);
      setError("Connection error");
      return false;
    }
  }, []);

  // Pause ingestion
  const pauseIngestion = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/pause`, {
        method: "POST",
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || "Failed to pause ingestion");
        return false;
      }

      return true;
    } catch (err) {
      console.error("Error pausing ingestion:", err);
      setError("Connection error");
      return false;
    }
  }, []);

  // Resume ingestion
  const resumeIngestion = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/resume`, {
        method: "POST",
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || "Failed to resume ingestion");
        return false;
      }

      return true;
    } catch (err) {
      console.error("Error resuming ingestion:", err);
      setError("Connection error");
      return false;
    }
  }, []);

  // Clean collections
  const cleanCollections = useCallback(
    async (request: CleanCollectionsRequest) => {
      setError(null);

      try {
        const response = await fetch(`${getApiBase()}/api/ingestion/clean`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
          setError(
            data.errors?.join(", ") ||
              data.message ||
              "Failed to clean collections",
          );
          return false;
        }

        // Refresh status to get updated collection counts
        fetchStatus();
        return true;
      } catch (err) {
        console.error("Error cleaning collections:", err);
        setError("Connection error");
        return false;
      }
    },
    [fetchStatus],
  );

  // Reindex (start with force reindex)
  const reindexCollections = useCallback(async (request: IngestionRequest) => {
    setError(null);
    setLastResult(null);

    try {
      const response = await fetch(`${getApiBase()}/api/ingestion/reindex`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        setError(data.error || data.message || "Failed to start reindex");
        return false;
      }

      return true;
    } catch (err) {
      console.error("Error starting reindex:", err);
      setError("Connection error");
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
    pauseIngestion,
    resumeIngestion,
    cleanCollections,
    reindexCollections,
    refreshStatus: fetchStatus,
  };
}
