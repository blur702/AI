import { useState, useEffect, useCallback, memo } from "react";
import { HealthStatus as HealthStatusType } from "../types";
import { getApiBase } from "../config/services";
import "./HealthStatus.css";

function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  const secs = Math.floor(seconds % 60);
  return `${minutes}m ${secs}s`;
}

function getStatusClass(status: HealthStatusType["status"]): string {
  const statusMap: Record<HealthStatusType["status"], string> = {
    healthy: "healthy",
    warning: "warning",
    error: "error",
  };
  return statusMap[status] || "error";
}

export const HealthStatus = memo(function HealthStatus() {
  const [health, setHealth] = useState<HealthStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBase()}/api/health`, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Health check failed");
      }

      const data: HealthStatusType = await response.json();
      setHealth(data);
      setError(false);
    } catch (err) {
      console.error("Health check error:", err);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();

    const interval = setInterval(fetchHealth, 30000);

    return () => clearInterval(interval);
  }, [fetchHealth]);

  if (loading) {
    return null;
  }

  // If error and no previous health data, show error state
  if (error && !health) {
    return (
      <div className="health-status error">
        <span className="health-indicator"></span>
        <span className="health-text">Health Check Failed</span>
      </div>
    );
  }

  if (!health) {
    return null;
  }

  const statusClass = getStatusClass(health.status);
  const statusLabel =
    health.status.charAt(0).toUpperCase() + health.status.slice(1);
  const isStale = error && health;

  return (
    <div
      className={`health-status ${statusClass}${isStale ? " stale" : ""}`}
      title={`CPU: ${health.cpu.percent.toFixed(1)}% | Memory: ${health.memory.percent.toFixed(1)}% | Services: ${health.services.running}/${health.services.total}${isStale ? " | Data may be stale" : ""}`}
    >
      <span className="health-indicator"></span>
      <span className="health-text">
        {statusLabel} • {formatUptime(health.uptime_seconds)}
        {isStale ? " (stale)" : ""}
      </span>
    </div>
  );
});
