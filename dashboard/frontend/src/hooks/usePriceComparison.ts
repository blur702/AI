import { useCallback, useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import {
  ComparisonResult,
  SearchProgress,
  SavedSelection,
  ProductSearchRequest,
} from "../types";
import { getApiBase } from "../config/services";

// Aggregation data from the backend best-price analysis
export interface SavedAggregation {
  service_totals: Record<string, number>;
  cheapest_service: string | null;
  cheapest_total: number | null;
  most_expensive_service: string | null;
  most_expensive_total: number | null;
  potential_savings: number;
  recommended_service: string | null;
}

interface UsePriceComparisonReturn {
  comparisonResult: ComparisonResult | null;
  loading: boolean;
  error: string | null;
  progress: SearchProgress | null;
  savedSelections: SavedSelection[];
  savedAggregation: SavedAggregation | null;
  searchProducts: (
    query: string,
    location?: string,
    services?: string[]
  ) => Promise<ComparisonResult | null>;
  getComparison: (comparisonId: string) => Promise<ComparisonResult | null>;
  saveSelection: (
    sessionToken: string,
    productId: string,
    quantity?: number
  ) => Promise<boolean>;
  deleteSelection: (
    selectionId: string,
    sessionToken: string
  ) => Promise<boolean>;
  getSavedSelections: (sessionToken: string) => Promise<void>;
  clearResults: () => void;
}

export function usePriceComparison(): UsePriceComparisonReturn {
  const [comparisonResult, setComparisonResult] =
    useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<SearchProgress | null>(null);
  const [savedSelections, setSavedSelections] = useState<SavedSelection[]>([]);
  const [savedAggregation, setSavedAggregation] = useState<SavedAggregation | null>(null);
  const socketRef = useRef<Socket | null>(null);

  // Initialize WebSocket connection
  useEffect(() => {
    const abortController = new AbortController();

    fetch(`${getApiBase()}/api/auth/token`, {
      credentials: "include",
      signal: abortController.signal,
    })
      .then((res) => {
        if (abortController.signal.aborted) return null;
        if (!res.ok) throw new Error("Authentication required");
        return res.json();
      })
      .then((data) => {
        if (!data || abortController.signal.aborted) return;

        const socket = io(getApiBase(), {
          transports: ["websocket", "polling"],
          auth: { token: data.token },
        });
        socketRef.current = socket;

        socket.on("connect_error", (err) => {
          console.error("Socket.IO connection error (price comparison):", err);
        });

        socket.on("disconnect", (reason) => {
          console.log("Socket.IO disconnected (price comparison):", reason);
        });

        socket.on("connect", () => {
          console.log("Socket.IO connected for price comparison");
        });

        // Listen for scraping progress updates
        socket.on("price_comparison_progress", (data: SearchProgress) => {
          setProgress(data);
        });

        // Listen for completion
        socket.on(
          "price_comparison_complete",
          (data: { comparison_id: string }) => {
            setProgress(null);
            // Optionally refresh the comparison result
            if (data.comparison_id) {
              // Could auto-fetch the result here
            }
          }
        );

        // Listen for errors
        socket.on(
          "price_comparison_error",
          (data: { error: string; service?: string }) => {
            console.error("Price comparison error:", data);
            setProgress(null);
          }
        );
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        console.error(
          "Socket.IO authentication failed (price comparison):",
          err
        );
      });

    return () => {
      abortController.abort();
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, []);

  const searchProducts = useCallback(
    async (
      query: string,
      location = "20024",
      services?: string[]
    ): Promise<ComparisonResult | null> => {
      setError(null);
      setLoading(true);
      setProgress(null);

      try {
        const payload: ProductSearchRequest = {
          query,
          location,
          services,
        };

        const response = await fetch(
          `${getApiBase()}/api/price-comparison/search`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify(payload),
          }
        );

        const data = await response.json();

        if (!response.ok) {
          const errorMsg =
            data.error || data.message || `Search failed (HTTP ${response.status})`;
          setError(errorMsg);
          setLoading(false);
          return null;
        }

        // Handle unified response wrapper
        const result: ComparisonResult = data.data || data;

        if (result.status === "error") {
          setError(result.errors?.[0] || "Search failed");
          setLoading(false);
          return null;
        }

        setComparisonResult(result);
        setLoading(false);
        return result;
      } catch (err) {
        console.error("Error searching products:", err);
        setError("Connection error while searching products");
        setLoading(false);
        return null;
      }
    },
    []
  );

  const getComparison = useCallback(
    async (comparisonId: string): Promise<ComparisonResult | null> => {
      setError(null);
      setLoading(true);

      try {
        const response = await fetch(
          `${getApiBase()}/api/price-comparison/comparison/${comparisonId}`,
          {
            method: "GET",
            credentials: "include",
          }
        );

        const data = await response.json();

        if (!response.ok) {
          const errorMsg =
            data.error ||
            data.message ||
            `Failed to fetch comparison (HTTP ${response.status})`;
          setError(errorMsg);
          setLoading(false);
          return null;
        }

        const result: ComparisonResult = data.data || data;
        setComparisonResult(result);
        setLoading(false);
        return result;
      } catch (err) {
        console.error("Error fetching comparison:", err);
        setError("Connection error while fetching comparison");
        setLoading(false);
        return null;
      }
    },
    []
  );

} catch (err) {
console.error("Error fetching saved selections:", err);
setError("Failed to load saved selections");
}

  const saveSelection = useCallback(
    async (
      sessionToken: string,
      productId: string,
      quantity = 1
    ): Promise<boolean> => {
      try {
        const params = new URLSearchParams({
          session_token: sessionToken,
          product_id: productId,
          quantity: quantity.toString(),
        });

        const response = await fetch(
          `${getApiBase()}/api/price-comparison/save?${params.toString()}`,
          {
            method: "POST",
            credentials: "include",
          }
        );

        const data = await response.json();

        if (!response.ok || !data.data?.saved) {
          setError(data.error || data.message || "Failed to save selection");
          return false;
        }

        // Refresh saved selections
        await getSavedSelections(sessionToken);
        return true;
      } catch (err) {
        console.error("Error saving selection:", err);
        setError("Connection error while saving selection");
        return false;
      }
    },
    [getSavedSelections]
  );

  const deleteSelection = useCallback(
    async (selectionId: string, sessionToken: string): Promise<boolean> => {
      try {
        const response = await fetch(
          `${getApiBase()}/api/price-comparison/saved/${selectionId}?session_token=${encodeURIComponent(sessionToken)}`,
          {
            method: "DELETE",
            credentials: "include",
          }
        );

        const data = await response.json();

        if (!response.ok || !data.data?.deleted) {
          setError(data.error || data.message || "Failed to delete selection");
          return false;
        }

        // Refresh saved selections
        await getSavedSelections(sessionToken);
        return true;
      } catch (err) {
        console.error("Error deleting selection:", err);
        setError("Connection error while deleting selection");
        return false;
      }
    },
    [getSavedSelections]
  );

  const clearResults = useCallback(() => {
    setComparisonResult(null);
    setError(null);
    setProgress(null);
  }, []);

  return {
    comparisonResult,
    loading,
    error,
    progress,
    savedSelections,
    savedAggregation,
    searchProducts,
    getComparison,
    saveSelection,
    deleteSelection,
    getSavedSelections,
    clearResults,
  };
}
