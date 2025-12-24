import { memo, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SortIcon from "@mui/icons-material/Sort";
import FilterListIcon from "@mui/icons-material/FilterList";
import { SelectChangeEvent } from "@mui/material/Select";
import { ProductGroup, Product, GROCERY_SERVICES } from "../types";
import { ProductCard } from "./ProductCard";

interface ComparisonTableProps {
  groups: ProductGroup[];
  onSaveProduct?: (productId: string) => void;
  loading?: boolean;
  servicesScraped?: string[];
  totalProducts?: number;
}

type SortOption = "price_asc" | "price_desc" | "service" | "similarity";

interface FilterState {
  availableOnly: boolean;
  organicOnly: boolean;
  services: string[];
}

function findLowestPriceProduct(products: Product[]): string | null {
  if (products.length === 0) return null;
  const available = products.filter((p) => p.availability);
  if (available.length === 0) return null;
  const lowest = available.reduce((min, p) => (p.price < min.price ? p : min));
  return lowest.id;
}

function sortProducts(products: Product[], sortBy: SortOption): Product[] {
  const sorted = [...products];
  switch (sortBy) {
    case "price_asc":
      return sorted.sort((a, b) => a.price - b.price);
    case "price_desc":
      return sorted.sort((a, b) => b.price - a.price);
    case "service":
      return sorted.sort((a, b) => a.service.localeCompare(b.service));
    case "similarity":
      return sorted.sort((a, b) => b.similarity_score - a.similarity_score);
    default:
      return sorted;
  }
}

function filterProducts(products: Product[], filters: FilterState): Product[] {
  return products.filter((p) => {
    if (filters.availableOnly && !p.availability) return false;
    if (filters.organicOnly && !p.attributes?.is_organic) return false;
    if (filters.services.length > 0 && !filters.services.includes(p.service)) {
      return false;
    }
    return true;
  });
}

export const ComparisonTable = memo(function ComparisonTable({
  groups,
  onSaveProduct,
  loading = false,
  servicesScraped = [],
  totalProducts = 0,
}: ComparisonTableProps) {
  const [sortBy, setSortBy] = useState<SortOption>("price_asc");
  const [filters, setFilters] = useState<FilterState>({
    availableOnly: false,
    organicOnly: false,
    services: [],
  });
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(groups.map((g) => g.representative_name)),
  );

  // Reset expanded groups when new search results arrive
  useEffect(() => {
    setExpandedGroups(new Set(groups.map((g) => g.representative_name)));
  }, [groups]);

  const handleSortChange = (event: SelectChangeEvent<SortOption>) => {
    setSortBy(event.target.value as SortOption);
  };

  const toggleFilter = (key: keyof Omit<FilterState, "services">) => {
    setFilters((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleServiceFilter = (serviceId: string) => {
    setFilters((prev) => ({
      ...prev,
      services: prev.services.includes(serviceId)
        ? prev.services.filter((s) => s !== serviceId)
        : [...prev.services, serviceId],
    }));
  };

  const handleAccordionChange = (groupName: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  };

  const processedGroups = useMemo(() => {
    return groups.map((group) => {
      const filtered = filterProducts(group.products, filters);
      const sorted = sortProducts(filtered, sortBy);
      const lowestPriceId = findLowestPriceProduct(sorted);
      return {
        ...group,
        products: sorted,
        lowestPriceId,
      };
    });
  }, [groups, filters, sortBy]);

  // Loading skeleton
  if (loading) {
    return (
      <Box>
        <Box sx={{ display: "flex", gap: 2, mb: 3 }}>
          <Skeleton variant="rectangular" width={150} height={40} />
          <Skeleton variant="rectangular" width={100} height={40} />
          <Skeleton variant="rectangular" width={100} height={40} />
        </Box>
        {[1, 2].map((i) => (
          <Box key={i} sx={{ mb: 3 }}>
            <Skeleton
              variant="rectangular"
              width="100%"
              height={60}
              sx={{ mb: 2 }}
            />
            <Grid container spacing={2}>
              {[1, 2, 3].map((j) => (
                <Grid item xs={12} sm={6} md={4} key={j}>
                  <Skeleton variant="rectangular" height={280} />
                </Grid>
              ))}
            </Grid>
          </Box>
        ))}
      </Box>
    );
  }

  // Empty state
  if (groups.length === 0) {
    return (
      <Box
        sx={{
          textAlign: "center",
          py: 6,
          px: 2,
          bgcolor: "action.hover",
          borderRadius: 2,
        }}
      >
        <Typography variant="h6" color="text.secondary" gutterBottom>
          No products found
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Try searching for a different product or adjusting your filters.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Stats and Controls */}
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          mb: 3,
        }}
      >
        {/* Stats */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {totalProducts} products in {groups.length} group(s)
          </Typography>
          {servicesScraped.length > 0 && (
            <Stack direction="row" spacing={0.5}>
              {servicesScraped.map((service) => (
                <Chip
                  key={service}
                  label={service.replace("_", " ")}
                  size="small"
                  sx={{
                    fontSize: "0.65rem",
                    height: 20,
                    textTransform: "capitalize",
                  }}
                />
              ))}
            </Stack>
          )}
        </Box>

        {/* Sort and Filter Controls */}
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {/* Sort Select */}
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel id="sort-select-label">
              <SortIcon
                sx={{ fontSize: 16, mr: 0.5, verticalAlign: "middle" }}
              />
              Sort
            </InputLabel>
            <Select
              labelId="sort-select-label"
              value={sortBy}
              onChange={handleSortChange}
              label="Sort"
            >
              <MenuItem value="price_asc">Price: Low to High</MenuItem>
              <MenuItem value="price_desc">Price: High to Low</MenuItem>
              <MenuItem value="service">By Service</MenuItem>
              <MenuItem value="similarity">By Match Score</MenuItem>
            </Select>
          </FormControl>

          {/* Filter Chips */}
          <Stack direction="row" spacing={0.5} alignItems="center">
            <FilterListIcon fontSize="small" color="action" />
            <Chip
              label="Available"
              size="small"
              variant={filters.availableOnly ? "filled" : "outlined"}
              color={filters.availableOnly ? "primary" : "default"}
              onClick={() => toggleFilter("availableOnly")}
              sx={{ cursor: "pointer" }}
            />
            <Chip
              label="Organic"
              size="small"
              variant={filters.organicOnly ? "filled" : "outlined"}
              color={filters.organicOnly ? "success" : "default"}
              onClick={() => toggleFilter("organicOnly")}
              sx={{ cursor: "pointer" }}
            />
          </Stack>
        </Box>
      </Box>

      {/* Service Filter Row */}
      <Box sx={{ mb: 3 }}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {GROCERY_SERVICES.map((service) => {
            const isActive =
              filters.services.length === 0 ||
              filters.services.includes(service.id);
            return (
              <Chip
                key={service.id}
                label={service.name}
                size="small"
                variant={isActive ? "filled" : "outlined"}
                onClick={() => toggleServiceFilter(service.id)}
                sx={{
                  cursor: "pointer",
                  bgcolor: isActive ? service.color : "transparent",
                  color: isActive ? "white" : "text.primary",
                  borderColor: service.color,
                  "&:hover": {
                    bgcolor: isActive ? service.color : `${service.color}22`,
                  },
                }}
              />
            );
          })}
        </Stack>
      </Box>

      {/* Product Groups */}
      {processedGroups.map((group) => (
        <Accordion
          key={group.representative_name}
          expanded={expandedGroups.has(group.representative_name)}
          onChange={() => handleAccordionChange(group.representative_name)}
          sx={{
            mb: 2,
            "&:before": { display: "none" },
            borderRadius: 1,
            overflow: "hidden",
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            sx={{
              bgcolor: "action.hover",
              "&:hover": { bgcolor: "action.selected" },
            }}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 2,
                width: "100%",
              }}
            >
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {group.representative_name}
              </Typography>
              <Chip
                label={`${group.products.length} product${group.products.length !== 1 ? "s" : ""}`}
                size="small"
                sx={{ fontSize: "0.7rem" }}
              />
              {group.lowestPriceId && (
                <Chip
                  label="Best price available"
                  size="small"
                  color="success"
                  sx={{ fontSize: "0.65rem" }}
                />
              )}
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 2, bgcolor: "background.paper" }}>
            {/* Group Reasoning */}
            {group.reasoning && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mb: 2, fontStyle: "italic" }}
              >
                {group.reasoning}
              </Typography>
            )}

            {/* Products Grid */}
            {group.products.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No products match the current filters.
              </Typography>
            ) : (
              <Grid container spacing={2}>
                {group.products.map((product) => (
                  <Grid item xs={12} sm={6} md={4} key={product.id}>
                    <ProductCard
                      product={product}
                      onSave={onSaveProduct}
                      highlighted={product.id === group.lowestPriceId}
                    />
                  </Grid>
                ))}
              </Grid>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
});
