import { memo, useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import CircularProgress from "@mui/material/CircularProgress";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import DownloadIcon from "@mui/icons-material/Download";
import RefreshIcon from "@mui/icons-material/Refresh";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { getApiBase } from "../config/services";
import { getServiceName, getServiceColor } from "../types";

interface ShoppingListItem {
  query: string;
  quantity: number;
  status: string;
  comparison_id?: string;
  error?: string;
  services_found?: string[];
}

interface TotalStats {
  service_totals: Record<string, number>;
  cheapest_service: string | null;
  most_expensive_service: string | null;
  potential_savings: number;
  items_processed: number;
  items_failed: number;
}

interface ShoppingListData {
  list_id: string;
  name: string;
  items: ShoppingListItem[];
  total_stats: TotalStats;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ShoppingListResultsProps {
  listId: string;
  onBack?: () => void;
}

export const ShoppingListResults = memo(function ShoppingListResults({
  listId,
  onBack,
}: ShoppingListResultsProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ShoppingListData | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${getApiBase()}/api/price-comparison/shopping-list/${listId}`,
        { credentials: "include" },
      );

      const result = await response.json();
      const listData = result.data || result;

      if (!response.ok || listData.status === "error") {
        setError(listData.message || "Failed to load shopping list");
        setData(null);
      } else {
        setData(listData);
      }
    } catch (err) {
      setError(`Failed to fetch shopping list: ${err}`);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [listId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleExportCSV = useCallback(() => {
    if (!data) return;

    const lines: string[] = [];
    lines.push("Shopping List Export");
    lines.push(`Name: ${data.name}`);
    lines.push(`Date: ${new Date(data.created_at).toLocaleString()}`);
    lines.push("");
    lines.push("Item,Quantity,Status");

    const sanitizeCSVField = (field: string): string => {
      // Prevent CSV injection by prefixing dangerous characters
      if (/^[=+\-@\t\r]/.test(field)) {
        return `'${field}`;
      }
      // Escape quotes and wrap in quotes if contains comma or quote
      if (field.includes(",") || field.includes('"') || field.includes("\n")) {
        return `"${field.replace(/"/g, '""')}"`;
      }
      return field;
    };
    // In handleExportCSV:
    for (const item of data.items) {
      lines.push(
        `${sanitizeCSVField(item.query)},${item.quantity},${item.status}`,
      );
    }

    lines.push("");
    lines.push("Service Totals:");
    lines.push("Service,Total");
    for (const [service, total] of Object.entries(
      data.total_stats.service_totals,
    )) {
      lines.push(`${getServiceName(service)},$${total.toFixed(2)}`);
    }

    lines.push("");
    lines.push(
      `Cheapest Service: ${getServiceName(data.total_stats.cheapest_service || "")}`,
    );
    lines.push(
      `Potential Savings: $${data.total_stats.potential_savings.toFixed(2)}`,
    );

    const csvContent = lines.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${data.name.replace(/\s+/g, "_")}_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }, [data]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircleIcon color="success" fontSize="small" />;
      case "error":
        return <ErrorIcon color="error" fontSize="small" />;
      default:
        return <CircularProgress size={16} />;
    }
  };

  // Loading state
  if (loading) {
    return (
      <Box>
        <Skeleton variant="rectangular" height={100} sx={{ mb: 2 }} />
        <Skeleton variant="rectangular" height={200} sx={{ mb: 2 }} />
        <Skeleton variant="rectangular" height={300} />
      </Box>
    );
  }

  // Error state
  if (error || !data) {
    return (
      <Alert
        severity="error"
        action={
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              size="small"
              onClick={fetchData}
              startIcon={<RefreshIcon />}
            >
              Retry
            </Button>
            {onBack && (
              <Button size="small" onClick={onBack}>
                Back
              </Button>
            )}
          </Box>
        }
      >
        {error || "Shopping list not found"}
      </Alert>
    );
  }

  const { items, total_stats, name, created_at } = data;
  const serviceTotals = Object.entries(total_stats.service_totals).sort(
    ([, a], [, b]) => a - b,
  );

  return (
    <Box>
      {/* Header */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
            }}
          >
            <Box>
              <Typography variant="h5" gutterBottom>
                {name}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Created: {new Date(created_at).toLocaleString()}
              </Typography>
              <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
                <Chip
                  label={`${total_stats.items_processed} items`}
                  size="small"
                />
                {total_stats.items_failed > 0 && (
                  <Chip
                    label={`${total_stats.items_failed} failed`}
                    size="small"
                    color="error"
                  />
                )}
              </Box>
            </Box>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button
                size="small"
                startIcon={<DownloadIcon />}
                onClick={handleExportCSV}
              >
                Export CSV
              </Button>
              {onBack && (
                <Button size="small" onClick={onBack}>
                  New Search
                </Button>
              )}
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Service Comparison */}
      {serviceTotals.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Price Comparison by Service
            </Typography>

            <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Service</TableCell>
                    <TableCell align="right">Total Cost</TableCell>
                    <TableCell align="right">Difference</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {serviceTotals.map(([service, total], index) => {
                    const cheapestTotal = serviceTotals[0][1];
                    const difference = total - cheapestTotal;
                    const isCheapest = index === 0;

                    return (
                      <TableRow
                        key={service}
                        sx={{
                          bgcolor: isCheapest ? "success.dark" : "transparent",
                        }}
                      >
                        <TableCell>
                          <Box
                            sx={{
                              display: "flex",
                              alignItems: "center",
                              gap: 1,
                            }}
                          >
                            <Box
                              sx={{
                                width: 16,
                                height: 16,
                                borderRadius: "50%",
                                bgcolor: getServiceColor(service),
                              }}
                            />
                            <Typography
                              sx={{ fontWeight: isCheapest ? 700 : 400 }}
                            >
                              {getServiceName(service)}
                            </Typography>
                            {isCheapest && (
                              <Chip
                                label="Best Price"
                                size="small"
                                color="success"
                                sx={{ ml: 1 }}
                              />
                            )}
                          </Box>
                        </TableCell>
                        <TableCell align="right">
                          <Typography
                            variant="h6"
                            sx={{ fontWeight: isCheapest ? 700 : 400 }}
                          >
                            ${total.toFixed(2)}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          {!isCheapest && (
                            <Typography color="error.main">
                              +${difference.toFixed(2)}
                            </Typography>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Potential Savings Banner */}
            {total_stats.potential_savings > 0 && (
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 2,
                  p: 2,
                  bgcolor: "success.dark",
                  borderRadius: 1,
                }}
              >
                <TrendingDownIcon sx={{ fontSize: 40 }} />
                <Box>
                  <Typography variant="h5" sx={{ fontWeight: 700 }}>
                    Save ${total_stats.potential_savings.toFixed(2)}
                  </Typography>
                  <Typography variant="body2">
                    by shopping at{" "}
                    {getServiceName(total_stats.cheapest_service || "")} instead
                    of{" "}
                    {getServiceName(total_stats.most_expensive_service || "")}
                  </Typography>
                </Box>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {/* Items List */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Items ({items.length})
          </Typography>

          {items.map((item, index) => (
            <Accordion
              key={item.comparison_id || `${item.query}-${index}`}
              defaultExpanded={item.status === "error"}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 2,
                    width: "100%",
                    pr: 2,
                  }}
                >
                  {getStatusIcon(item.status)}
                  <Typography sx={{ flexGrow: 1, fontWeight: 500 }}>
                    {item.query}
                  </Typography>
                  <Chip label={`x${item.quantity}`} size="small" />
                  {item.services_found && item.services_found.length > 0 && (
                    <Chip
                      label={`${item.services_found.length} services`}
                      size="small"
                      variant="outlined"
                    />
                  )}
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                {item.error ? (
                  <Alert severity="error" sx={{ mb: 1 }}>
                    {item.error}
                  </Alert>
                ) : (
                  <Box>
                    {item.services_found && item.services_found.length > 0 && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="caption" color="text.secondary">
                          Found at:
                        </Typography>
                        <Box
                          sx={{
                            display: "flex",
                            gap: 0.5,
                            mt: 0.5,
                            flexWrap: "wrap",
                          }}
                        >
                          {item.services_found.map((service) => (
                            <Chip
                              key={service}
                              label={getServiceName(service)}
                              size="small"
                              sx={{
                                bgcolor: getServiceColor(service),
                                color: "white",
                              }}
                            />
                          ))}
                        </Box>
                      </Box>
                    )}
                    {item.comparison_id && (
                      <Button
                        size="small"
                        startIcon={<OpenInNewIcon />}
                        onClick={() => {
                          // Could navigate to detailed comparison view
                          console.log("View comparison:", item.comparison_id);
                        }}
                      >
                        View Full Comparison
                      </Button>
                    )}
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          ))}
        </CardContent>
      </Card>
    </Box>
  );
});
