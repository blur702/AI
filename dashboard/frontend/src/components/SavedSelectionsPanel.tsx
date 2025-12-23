import { memo, useCallback, useMemo } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import ListItemSecondaryAction from "@mui/material/ListItemSecondaryAction";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Grid from "@mui/material/Grid";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import StorefrontIcon from "@mui/icons-material/Storefront";
import { SavedSelection, getServiceName, getServiceColor } from "../types";
import type { SavedAggregation } from "../hooks/usePriceComparison";

interface SavedSelectionsPanelProps {
  selections: SavedSelection[];
  aggregation?: SavedAggregation | null;
  onDelete: (selectionId: string) => void;
  loading?: boolean;
}

export const SavedSelectionsPanel = memo(function SavedSelectionsPanel({
  selections,
  aggregation,
  onDelete,
  loading = false,
}: SavedSelectionsPanelProps) {
  // Calculate total
  const total = useMemo(() => {
    return selections.reduce(
      (acc, s) => acc + (s.product?.price ?? 0) * s.quantity,
      0
    );
  }, [selections]);

  // Export to CSV
  const handleExportCSV = useCallback(() => {
    if (selections.length === 0) return;

    const lines: string[] = [];
    lines.push("Product Name,Service,Price,Quantity,Subtotal");

    for (const selection of selections) {
      const product = selection.product;
      if (!product) continue;
      const subtotal = product.price * selection.quantity;
      lines.push(
        `"${product.name}",${getServiceName(product.service)},$${product.price.toFixed(2)},${selection.quantity},$${subtotal.toFixed(2)}`
      );
    }

    lines.push("");
    lines.push(`Total,,,${selections.length},$${total.toFixed(2)}`);

    const csvContent = lines.join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `saved_selections_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }, [selections, total]);

  // Export to JSON
  const handleExportJSON = useCallback(() => {
    if (selections.length === 0) return;

    const exportData = {
      exported_at: new Date().toISOString(),
      total_items: selections.length,
      total_value: total,
      selections: selections.map((s) => ({
        product_name: s.product?.name,
        service: s.product?.service,
        price: s.product?.price,
        quantity: s.quantity,
        subtotal: (s.product?.price ?? 0) * s.quantity,
        notes: s.notes,
        url: s.product?.url,
      })),
    };

    const jsonContent = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonContent], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `saved_selections_${new Date().toISOString().split("T")[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [selections, total]);

  // Loading state
  if (loading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="rectangular" height={60} sx={{ mb: 2 }} />
          <Skeleton variant="rectangular" height={60} sx={{ mb: 2 }} />
          <Skeleton variant="rectangular" height={60} />
        </CardContent>
      </Card>
    );
  }

  // Empty state
  if (selections.length === 0) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ textAlign: "center", py: 6 }}>
            <ShoppingCartIcon
              sx={{ fontSize: 48, color: "text.secondary", mb: 2 }}
            />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No saved selections yet
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Click "Save" on a product to add it to your list.
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Best Price Insights */}
      {aggregation && aggregation.cheapest_service && (
        <Card sx={{ bgcolor: "success.dark" }}>
          <CardContent>
            <Grid container spacing={2}>
              {/* Recommended Service */}
              <Grid item xs={12} md={4}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                  <StorefrontIcon sx={{ fontSize: 36 }} />
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Best Overall Price
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {getServiceName(aggregation.cheapest_service)}
                    </Typography>
                    {aggregation.cheapest_total && (
                      <Typography variant="body2" color="text.secondary">
                        ${aggregation.cheapest_total.toFixed(2)} total
                      </Typography>
                    )}
                  </Box>
                </Box>
              </Grid>

              {/* Potential Savings */}
              {aggregation.potential_savings > 0 && (
                <Grid item xs={12} md={4}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                    <TrendingDownIcon sx={{ fontSize: 36 }} />
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Potential Savings
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 700 }}>
                        ${aggregation.potential_savings.toFixed(2)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        by switching to cheapest options
                      </Typography>
                    </Box>
                  </Box>
                </Grid>
              )}

              {/* Service Comparison */}
              <Grid item xs={12} md={4}>
                <Typography variant="caption" color="text.secondary">
                  Price by Service
                </Typography>
                <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 1 }}>
                  {Object.entries(aggregation.service_totals)
                    .sort((a, b) => a[1] - b[1])
                    .map(([service, serviceTotal]) => (
                      <Chip
                        key={service}
                        label={`${getServiceName(service)}: $${serviceTotal.toFixed(2)}`}
                        size="small"
                        sx={{
                          bgcolor: getServiceColor(service),
                          color: "white",
                          fontWeight: service === aggregation.cheapest_service ? 700 : 400,
                        }}
                      />
                    ))}
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Selections Card */}
      <Card>
        <CardContent>
          {/* Selection List */}
          <List>
          {selections.map((selection) => (
            <ListItem
              key={selection.selection_id}
              divider
              sx={{
                "&:hover": {
                  bgcolor: "action.hover",
                },
              }}
            >
              <ListItemText
                primary={
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>
                    {selection.product?.name ?? "Unknown Product"}
                  </Typography>
                }
                secondary={
                  <Box
                    component="span"
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                      mt: 0.5,
                    }}
                  >
                    {selection.product && (
                      <>
                        <Chip
                          label={getServiceName(selection.product.service)}
                          size="small"
                          sx={{
                            bgcolor: getServiceColor(selection.product.service),
                            color: "white",
                            fontSize: "0.65rem",
                          }}
                        />
                        <Typography
                          variant="body2"
                          component="span"
                          color="primary"
                          sx={{ fontWeight: 600 }}
                        >
                          ${selection.product.price.toFixed(2)}
                        </Typography>
                        <Typography
                          variant="caption"
                          component="span"
                          color="text.secondary"
                        >
                          x{selection.quantity}
                        </Typography>
                        <Typography
                          variant="body2"
                          component="span"
                          color="text.secondary"
                          sx={{ ml: 1 }}
                        >
                          = ${(selection.product.price * selection.quantity).toFixed(2)}
                        </Typography>
                      </>
                    )}
                  </Box>
                }
              />
              <ListItemSecondaryAction>
                <IconButton
                  edge="end"
                  onClick={() => onDelete(selection.selection_id)}
                  size="small"
                  color="error"
                  title="Remove from list"
                >
                  <DeleteIcon />
                </IconButton>
              </ListItemSecondaryAction>
            </ListItem>
          ))}
        </List>

        <Divider sx={{ my: 2 }} />

        {/* Total and Export */}
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 2,
          }}
        >
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
              Total ({selections.length} items)
            </Typography>
            <Typography variant="h5" color="primary" sx={{ fontWeight: 700 }}>
              ${total.toFixed(2)}
            </Typography>
          </Box>

          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={handleExportCSV}
            >
              Export CSV
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={handleExportJSON}
            >
              Export JSON
            </Button>
          </Box>
        </Box>
      </CardContent>
    </Card>
    </Box>
  );
});
