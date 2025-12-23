import { memo, useCallback, useEffect, useRef, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import CircularProgress from "@mui/material/CircularProgress";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import CloseIcon from "@mui/icons-material/Close";
import DeleteIcon from "@mui/icons-material/Delete";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import { getApiBase } from "../config/services";
import { getServiceName, getServiceColor } from "../types";

/**
 * Expected CSV/TXT file format:
 * CSV: "product name, quantity" per line (quantity optional, defaults to 1)
 * TXT: One product per line, quantity defaults to 1
 *
 * Examples:
 *   milk, 2
 *   bread
 *   eggs, 12
 *   orange juice
 */

interface ParsedItem {
  query: string;
  quantity: number;
}

interface ProcessedItem {
  query: string;
  quantity: number;
  status: "pending" | "processing" | "completed" | "error";
  comparison_id?: string;
  error?: string;
}

interface TotalStats {
  service_totals: Record<string, number>;
  cheapest_service: string | null;
  most_expensive_service: string | null;
  potential_savings: number;
  items_processed: number;
  items_failed: number;
}

interface ProgressUpdate {
  status: string;
  progress?: {
    items_completed: number;
    total_items: number;
    current_item: string;
    percentage: number;
  };
  list_id?: string;
  items?: ProcessedItem[];
  total_stats?: TotalStats;
  error?: string;
}

interface BulkUploadDialogProps {
  open: boolean;
  onClose: () => void;
  onComplete: (listId: string) => void;
  sessionToken: string;
}

function parseFile(content: string, fileName: string): ParsedItem[] {
  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  const items: ParsedItem[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    // Try CSV format first (comma-separated)
    if (fileName.endsWith(".csv") || trimmed.includes(",")) {
      const parts = trimmed.split(",").map((p) => p.trim());
      const query = parts[0];
      const quantity = parts[1] ? parseInt(parts[1], 10) : 1;

      if (query) {
        items.push({
          query,
          quantity: isNaN(quantity) || quantity < 1 ? 1 : quantity,
        });
      }
    } else {
      // Plain text format - one item per line
      items.push({ query: trimmed, quantity: 1 });
    }
  }

  return items;
}

export const BulkUploadDialog = memo(function BulkUploadDialog({
  open,
  onClose,
  onComplete,
  sessionToken,
}: BulkUploadDialogProps) {
  const [listName, setListName] = useState("Shopping List");
  const [manualInput, setManualInput] = useState("");
  const [parsedItems, setParsedItems] = useState<ParsedItem[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listId, setListId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressUpdate["progress"] | null>(null);
  const [items, setItems] = useState<ProcessedItem[]>([]);
  const [totalStats, setTotalStats] = useState<TotalStats | null>(null);
  const [completed, setCompleted] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Clean up WebSocket on unmount or dialog close
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setListName("Shopping List");
      setManualInput("");
      setParsedItems([]);
      setFileName(null);
      setUploading(false);
      setProcessing(false);
      setError(null);
      setListId(null);
      setProgress(null);
      setItems([]);
      setTotalStats(null);
      setCompleted(false);
    }
  }, [open]);

  const handleFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      setError(null);
      setFileName(file.name);

      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        try {
          const parsed = parseFile(content, file.name);
          if (parsed.length === 0) {
            setError("No valid items found in file");
            setParsedItems([]);
          } else if (parsed.length > 100) {
            setError("Maximum 100 items allowed");
            setParsedItems([]);
          } else {
            setParsedItems(parsed);
            setManualInput("");
          }
        } catch (err) {
          setError(`Failed to parse file: ${err}`);
          setParsedItems([]);
        }
      };
      reader.onerror = () => {
        setError("Failed to read file");
      };
      reader.readAsText(file);
    },
    []
  );

  const handleManualInputChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = event.target.value;
      setManualInput(value);
      setFileName(null);

      if (value.trim()) {
        const parsed = parseFile(value, "manual.txt");
        setParsedItems(parsed);
      } else {
        setParsedItems([]);
      }
    },
    []
  );

  const handleRemoveItem = useCallback((index: number) => {
    setParsedItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const connectWebSocket = useCallback((jobId: string) => {
    const baseUrl = getApiBase();
    const wsProtocol = baseUrl.startsWith("https") ? "wss" : "ws";
    const wsHost = baseUrl.replace(/^https?:\/\//, "");
    const wsUrl = `${wsProtocol}://${wsHost}/api/jobs/ws/jobs/${jobId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected for job:", jobId);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Job system wraps progress in result field - extract the inner payload
        const payload: ProgressUpdate = data.result || data;

        if (payload.progress) {
          setProgress(payload.progress);
        }
        if (payload.list_id) {
          setListId(payload.list_id);
        }
        if (payload.items) {
          // Merge incoming items with existing state instead of replacing
          // This preserves pending items that haven't been processed yet
          setItems((prevItems) => {
            const updatedItems = [...prevItems];
            for (const incomingItem of payload.items!) {
              const existingIndex = updatedItems.findIndex(
                (item) => item.query === incomingItem.query
              );
              if (existingIndex >= 0) {
                updatedItems[existingIndex] = incomingItem;
              } else {
                updatedItems.push(incomingItem);
              }
            }
            return updatedItems;
          });
        }
        if (payload.total_stats) {
          setTotalStats(payload.total_stats);
        }

        if (payload.status === "completed") {
          setProcessing(false);
          setCompleted(true);
          ws.close();
        } else if (payload.status === "error" || payload.status === "failed") {
          setProcessing(false);
          setError(payload.error || "Processing failed");
          ws.close();
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
      }
    };

    ws.onerror = (event) => {
      console.error("WebSocket error:", event);
      setError("WebSocket connection error");
      setProcessing(false);
    };

    ws.onclose = () => {
      console.log("WebSocket closed");
      wsRef.current = null;
    };
  }, []);

  const handleUpload = useCallback(async () => {
    if (parsedItems.length === 0) {
      setError("No items to upload");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const response = await fetch(`${getApiBase()}/api/price-comparison/bulk-upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          items: parsedItems.map((item) => ({
            query: item.query,
            quantity: item.quantity,
          })),
          session_token: sessionToken,
          name: listName,
        }),
      });

      const data = await response.json();
      const result = data.data || data;

      if (!response.ok || result.status === "error") {
        setError(result.message || "Upload failed");
        setUploading(false);
        return;
      }

      // Start WebSocket connection for progress updates
      setUploading(false);
      setProcessing(true);

      // Initialize items as pending
      setItems(
        parsedItems.map((item) => ({
          query: item.query,
          quantity: item.quantity,
          status: "pending" as const,
        }))
      );

      connectWebSocket(result.job_id);
    } catch (err) {
      setError(`Upload failed: ${err}`);
      setUploading(false);
    }
  }, [parsedItems, sessionToken, listName, connectWebSocket]);

  const handleClose = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    onClose();
  }, [onClose]);

  const handleViewResults = useCallback(() => {
    if (listId) {
      onComplete(listId);
    }
    handleClose();
  }, [listId, onComplete, handleClose]);

  const getItemIcon = (status: ProcessedItem["status"]) => {
    switch (status) {
      case "completed":
        return <CheckCircleIcon color="success" fontSize="small" />;
      case "error":
        return <ErrorIcon color="error" fontSize="small" />;
      case "processing":
        return <CircularProgress size={16} />;
      default:
        return <HourglassEmptyIcon color="disabled" fontSize="small" />;
    }
  };

  const isUploading = uploading || processing;
  const canUpload = parsedItems.length > 0 && !isUploading && !completed;

  return (
    <Dialog
      open={open}
      onClose={!isUploading ? handleClose : undefined}
      maxWidth="md"
      fullWidth
      disableEscapeKeyDown={isUploading}
    >
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <UploadFileIcon />
        Upload Shopping List
        {!isUploading && (
          <IconButton
            onClick={handleClose}
            sx={{ position: "absolute", right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        )}
      </DialogTitle>

      <DialogContent dividers>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {!processing && !completed && (
          <>
            {/* List Name Input */}
            <TextField
              fullWidth
              label="List Name"
              value={listName}
              onChange={(e) => setListName(e.target.value)}
              size="small"
              sx={{ mb: 2 }}
              disabled={isUploading}
            />

            {/* File Upload */}
            <Box
              sx={{
                border: "2px dashed",
                borderColor: "divider",
                borderRadius: 2,
                p: 3,
                textAlign: "center",
                mb: 2,
                cursor: isUploading ? "default" : "pointer",
                "&:hover": {
                  borderColor: isUploading ? "divider" : "primary.main",
                  bgcolor: isUploading ? "transparent" : "action.hover",
                },
              }}
              onClick={() => !isUploading && fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                accept=".csv,.txt"
                onChange={handleFileSelect}
                style={{ display: "none" }}
                disabled={isUploading}
              />
              <UploadFileIcon sx={{ fontSize: 40, color: "text.secondary", mb: 1 }} />
              <Typography variant="body1" gutterBottom>
                {fileName || "Drop a CSV or TXT file here, or click to browse"}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Format: One product per line, optionally with quantity (e.g., "milk, 2")
              </Typography>
            </Box>

            {/* Manual Input */}
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Or enter items manually:
            </Typography>
            <TextField
              fullWidth
              multiline
              rows={4}
              placeholder="Enter items, one per line:&#10;milk, 2&#10;bread&#10;eggs, 12"
              value={manualInput}
              onChange={handleManualInputChange}
              size="small"
              sx={{ mb: 2 }}
              disabled={isUploading}
            />

            {/* Preview */}
            {parsedItems.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Preview ({parsedItems.length} items):
                </Typography>
                <Box
                  sx={{
                    maxHeight: 200,
                    overflow: "auto",
                    border: 1,
                    borderColor: "divider",
                    borderRadius: 1,
                    p: 1,
                  }}
                >
                  {parsedItems.map((item, index) => (
                    <Box
                      key={index}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        py: 0.5,
                        px: 1,
                        "&:hover": { bgcolor: "action.hover" },
                      }}
                    >
                      <Typography variant="body2">
                        {item.query}{" "}
                        <Chip label={`x${item.quantity}`} size="small" sx={{ ml: 1 }} />
                      </Typography>
                      <Tooltip title="Remove">
                        <IconButton size="small" onClick={() => handleRemoveItem(index)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  ))}
                </Box>
              </Box>
            )}
          </>
        )}

        {/* Progress Section */}
        {(processing || completed) && (
          <Box>
            {/* Progress Bar */}
            {progress && (
              <Box sx={{ mb: 3 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2">
                    Processing: {progress.current_item}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {progress.items_completed} / {progress.total_items}
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={progress.percentage}
                  sx={{ height: 8, borderRadius: 1 }}
                />
              </Box>
            )}

            {/* Completion Message */}
            {completed && totalStats && (
              <Alert
                severity="success"
                sx={{ mb: 2 }}
                icon={<CheckCircleIcon />}
              >
                <Typography variant="subtitle2">
                  Processing complete! {totalStats.items_processed} items processed
                  {totalStats.items_failed > 0 && `, ${totalStats.items_failed} failed`}
                </Typography>
              </Alert>
            )}

            {/* Service Totals */}
            {totalStats && Object.keys(totalStats.service_totals).length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Price by Service:
                </Typography>
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Service</TableCell>
                        <TableCell align="right">Total</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(totalStats.service_totals)
                        .sort(([, a], [, b]) => a - b)
                        .map(([service, total], index) => (
                          <TableRow
                            key={service}
                            sx={{
                              bgcolor:
                                service === totalStats.cheapest_service
                                  ? "success.dark"
                                  : "transparent",
                            }}
                          >
                            <TableCell>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                                <Box
                                  sx={{
                                    width: 12,
                                    height: 12,
                                    borderRadius: "50%",
                                    bgcolor: getServiceColor(service),
                                  }}
                                />
                                {getServiceName(service)}
                                {index === 0 && (
                                  <Chip
                                    label="Cheapest"
                                    size="small"
                                    color="success"
                                    sx={{ ml: 1, fontSize: "0.6rem" }}
                                  />
                                )}
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography
                                sx={{ fontWeight: index === 0 ? 700 : 400 }}
                              >
                                ${total.toFixed(2)}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                    </TableBody>
                  </Table>
                </TableContainer>

                {/* Potential Savings */}
                {totalStats.potential_savings > 0 && (
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                      mt: 2,
                      p: 1.5,
                      bgcolor: "success.dark",
                      borderRadius: 1,
                    }}
                  >
                    <TrendingDownIcon />
                    <Typography variant="body2">
                      Potential savings by choosing {getServiceName(totalStats.cheapest_service || "")}:
                      <strong> ${totalStats.potential_savings.toFixed(2)}</strong>
                    </Typography>
                  </Box>
                )}
              </Box>
            )}

            {/* Items List */}
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Items:
              </Typography>
              <List
                dense
                sx={{
                  maxHeight: 200,
                  overflow: "auto",
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                }}
              >
                {items.map((item, index) => (
                  <ListItem key={index}>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      {getItemIcon(item.status)}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.query}
                      secondary={
                        item.error
                          ? item.error
                          : item.status === "completed"
                            ? "Completed"
                            : item.status === "processing"
                              ? "Processing..."
                              : "Pending"
                      }
                      secondaryTypographyProps={{
                        color: item.error ? "error" : "text.secondary",
                        fontSize: "0.75rem",
                      }}
                    />
                    <Chip label={`x${item.quantity}`} size="small" />
                  </ListItem>
                ))}
              </List>
            </Box>
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        {!completed ? (
          <>
            <Button onClick={handleClose} disabled={isUploading}>
              Cancel
            </Button>
            <Button
              variant="contained"
              onClick={handleUpload}
              disabled={!canUpload}
              startIcon={
                isUploading ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <UploadFileIcon />
                )
              }
            >
              {uploading ? "Uploading..." : processing ? "Processing..." : "Upload & Compare"}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose}>Close</Button>
            {listId && (
              <Button variant="contained" onClick={handleViewResults}>
                View Results
              </Button>
            )}
          </>
        )}
      </DialogActions>
    </Dialog>
  );
});
