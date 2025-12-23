import { memo, useMemo } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Grid from "@mui/material/Grid";
import Skeleton from "@mui/material/Skeleton";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import BarChartIcon from "@mui/icons-material/BarChart";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import {
  ComparisonResult,
  Product,
  getServiceName,
  getServiceColor,
} from "../types";

// Service colors for charts
const SERVICE_COLORS: Record<string, string> = {
  amazon_fresh: "#FF9900",
  instacart: "#43B02A",
  doordash: "#FF3008",
  safeway: "#E31837",
};

interface ServiceStats {
  service: string;
  totalPrice: number;
  productCount: number;
  avgPrice: number;
}

interface BestDeal {
  product: Product;
  savings: number;
  comparedTo: string;
}

interface StatisticsPanelProps {
  comparisonResult: ComparisonResult | null;
  loading?: boolean;
}

export const StatisticsPanel = memo(function StatisticsPanel({
  comparisonResult,
  loading = false,
}: StatisticsPanelProps) {
  // Calculate statistics from comparison results
  const statistics = useMemo(() => {
    if (!comparisonResult || comparisonResult.groups.length === 0) {
      return { serviceStats: [], bestDeals: [], potentialSavings: 0 };
    }

    const allProducts: Product[] = comparisonResult.groups.flatMap(
      (g) => g.products
    );

    // Group by service
    const byService = allProducts.reduce(
      (acc, product) => {
        if (!acc[product.service]) {
          acc[product.service] = { products: [], total: 0 };
        }
        acc[product.service].products.push(product);
        acc[product.service].total += product.price;
        return acc;
      },
      {} as Record<string, { products: Product[]; total: number }>
    );

    const serviceStats: ServiceStats[] = Object.entries(byService).map(
      ([service, data]) => ({
        service,
        totalPrice: data.total,
        productCount: data.products.length,
        avgPrice: data.total / data.products.length,
      })
    );

    // Sort by total price
    serviceStats.sort((a, b) => a.totalPrice - b.totalPrice);

    // Find best deals (products significantly cheaper than alternatives)
    const bestDeals: BestDeal[] = [];
    comparisonResult.groups.forEach((group) => {
      if (group.products.length < 2) return;

      const sorted = [...group.products].sort((a, b) => a.price - b.price);
      const cheapest = sorted[0];
      const nextCheapest = sorted[1];

      if (cheapest && nextCheapest) {
        const savings = nextCheapest.price - cheapest.price;
        if (savings > 0.5) {
          bestDeals.push({
            product: cheapest,
            savings,
            comparedTo: nextCheapest.service,
          });
        }
      }
    });

    // Sort by savings descending
    bestDeals.sort((a, b) => b.savings - a.savings);

    // Calculate potential savings
    const potentialSavings = bestDeals.reduce((acc, d) => acc + d.savings, 0);

    return { serviceStats, bestDeals: bestDeals.slice(0, 5), potentialSavings };
  }, [comparisonResult]);

  // Prepare chart data
  const barChartData = useMemo(() => {
    return statistics.serviceStats.map((stat) => ({
      name: getServiceName(stat.service),
      service: stat.service,
      total: stat.totalPrice,
      count: stat.productCount,
      avg: stat.avgPrice,
    }));
  }, [statistics.serviceStats]);

  const pieChartData = useMemo(() => {
    const totalValue = statistics.serviceStats.reduce(
      (acc, s) => acc + s.totalPrice,
      0
    );
    return statistics.serviceStats.map((stat) => ({
      name: getServiceName(stat.service),
      service: stat.service,
      value: stat.totalPrice,
      percentage:
        totalValue > 0 ? ((stat.totalPrice / totalValue) * 100).toFixed(1) : 0,
    }));
  }, [statistics.serviceStats]);

  // Loading state
  if (loading) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <Skeleton variant="rectangular" height={100} />
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Skeleton variant="rectangular" height={300} />
          </Grid>
          <Grid item xs={12} md={6}>
            <Skeleton variant="rectangular" height={300} />
          </Grid>
        </Grid>
      </Box>
    );
  }

  // Empty state
  if (!comparisonResult) {
    return (
      <Box
        sx={{
          textAlign: "center",
          py: 6,
          bgcolor: "action.hover",
          borderRadius: 2,
        }}
      >
        <BarChartIcon sx={{ fontSize: 48, color: "text.secondary", mb: 2 }} />
        <Typography variant="h6" color="text.secondary" gutterBottom>
          No statistics available
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Run a search to see price comparison statistics
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {/* Potential Savings Banner */}
      {statistics.potentialSavings > 0 && (
        <Card sx={{ bgcolor: "success.dark" }}>
          <CardContent
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 2,
            }}
          >
            <TrendingDownIcon sx={{ fontSize: 40 }} />
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                ${statistics.potentialSavings.toFixed(2)}
              </Typography>
              <Typography variant="body2">
                Potential savings by choosing the lowest price for each item
              </Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Charts Row */}
      <Grid container spacing={3}>
        {/* Service Price Comparison Bar Chart */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
                Service Price Comparison
              </Typography>
              {barChartData.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No price data available
                </Typography>
              ) : (
                <Box sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={barChartData} layout="vertical">
                      <XAxis
                        type="number"
                        tickFormatter={(value: number) => `$${value.toFixed(0)}`}
                      />
                      <YAxis type="category" dataKey="name" width={100} />
                      <RechartsTooltip
                        formatter={(value: number) => [
                          `$${value.toFixed(2)}`,
                          "Total",
                        ]}
                        labelStyle={{ color: "#000" }}
                      />
                      <Bar dataKey="total" name="Total Price">
                        {barChartData.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={
                              SERVICE_COLORS[entry.service] ||
                              getServiceColor(entry.service)
                            }
                            opacity={index === 0 ? 1 : 0.7}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Price Distribution Pie Chart */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
                Price Distribution
              </Typography>
              {pieChartData.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No distribution data available
                </Typography>
              ) : (
                <Box sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieChartData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={({ name, percentage }: { name: string; percentage: string | number }) => `${name}: ${percentage}%`}
                        labelLine
                      >
                        {pieChartData.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={
                              SERVICE_COLORS[entry.service] ||
                              getServiceColor(entry.service)
                            }
                          />
                        ))}
                      </Pie>
                      <Legend />
                      <RechartsTooltip
                        formatter={(value: number) => `$${value.toFixed(2)}`}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Best Deals */}
      {statistics.bestDeals.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
              Top 5 Best Deals
            </Typography>
            <List disablePadding>
              {statistics.bestDeals.map((deal, index) => (
                <ListItem
                  key={deal.product.id}
                  divider={index < statistics.bestDeals.length - 1}
                  sx={{ px: 0 }}
                >
                  <ListItemText
                    primary={
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                        }}
                      >
                        <Chip
                          label={getServiceName(deal.product.service)}
                          size="small"
                          sx={{
                            bgcolor: getServiceColor(deal.product.service),
                            color: "white",
                            fontSize: "0.65rem",
                          }}
                        />
                        <Typography
                          variant="body2"
                          sx={{
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            maxWidth: 300,
                          }}
                        >
                          {deal.product.name}
                        </Typography>
                      </Box>
                    }
                    secondary={`$${deal.product.price.toFixed(2)} vs ${getServiceName(deal.comparedTo)}`}
                  />
                  <Chip
                    icon={<TrendingDownIcon />}
                    label={`Save $${deal.savings.toFixed(2)}`}
                    color="success"
                    size="small"
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      )}

      {/* Detailed Service Comparison Table */}
      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
            Detailed Service Comparison
          </Typography>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Service</TableCell>
                  <TableCell align="right">Products</TableCell>
                  <TableCell align="right">Avg Price</TableCell>
                  <TableCell align="right">Total</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {statistics.serviceStats.map((stat, index) => (
                  <TableRow
                    key={stat.service}
                    sx={{
                      bgcolor: index === 0 ? "success.dark" : "transparent",
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
                            width: 12,
                            height: 12,
                            borderRadius: "50%",
                            bgcolor: getServiceColor(stat.service),
                          }}
                        />
                        {getServiceName(stat.service)}
                        {index === 0 && (
                          <Chip
                            label="Lowest"
                            size="small"
                            color="success"
                            sx={{ ml: 1, fontSize: "0.6rem" }}
                          />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell align="right">{stat.productCount}</TableCell>
                    <TableCell align="right">
                      ${stat.avgPrice.toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      <Typography
                        sx={{
                          fontWeight: index === 0 ? 700 : 400,
                        }}
                      >
                        ${stat.totalPrice.toFixed(2)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Box>
  );
});
