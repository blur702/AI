import { memo, useState, type KeyboardEvent } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import CircularProgress from "@mui/material/CircularProgress";
import InputAdornment from "@mui/material/InputAdornment";
import SearchIcon from "@mui/icons-material/Search";
import LocationOnIcon from "@mui/icons-material/LocationOn";
import { SelectChangeEvent } from "@mui/material/Select";
import { GROCERY_SERVICES } from "../types";

interface ProductSearchBarProps {
  onSearch: (query: string, location: string, services: string[]) => void;
  loading?: boolean;
  disabled?: boolean;
}

export const ProductSearchBar = memo(function ProductSearchBar({
  onSearch,
  loading = false,
  disabled = false,
}: ProductSearchBarProps) {
  const [query, setQuery] = useState<string>("");
  const [location, setLocation] = useState<string>("20024");
  const [selectedServices, setSelectedServices] = useState<string[]>(
    GROCERY_SERVICES.map((s) => s.id),
  );

  const handleServiceChange = (event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setSelectedServices(typeof value === "string" ? value.split(",") : value);
  };

  const handleSearch = () => {
    if (query.trim()) {
      onSearch(query.trim(), location, selectedServices);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && query.trim() && !loading && !disabled) {
      handleSearch();
    }
  };

  const handleRemoveService = (serviceId: string) => {
    setSelectedServices((prev) => prev.filter((s) => s !== serviceId));
  };

  return (
    <Box sx={{ width: "100%" }}>
      {/* Main search row */}
      <Box
        sx={{
          display: "flex",
          gap: 2,
          mb: 2,
          flexWrap: { xs: "wrap", md: "nowrap" },
        }}
      >
        {/* Search input */}
        <TextField
          fullWidth
          size="small"
          placeholder="Search for a product (e.g., milk, bread, eggs)..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || loading}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" color="action" />
              </InputAdornment>
            ),
          }}
          sx={{ minWidth: 200 }}
        />

        {/* Location input */}
        <TextField
          size="small"
          placeholder="ZIP Code"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          disabled={disabled || loading}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <LocationOnIcon fontSize="small" color="action" />
              </InputAdornment>
            ),
          }}
          sx={{ width: { xs: "100%", sm: 140 } }}
        />

        {/* Service selector */}
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="service-select-label">Services</InputLabel>
          <Select
            labelId="service-select-label"
            multiple
            value={selectedServices}
            onChange={handleServiceChange}
            input={<OutlinedInput label="Services" />}
            disabled={disabled || loading}
            renderValue={(selected) => `${selected.length} selected`}
          >
            {GROCERY_SERVICES.map((service) => (
              <MenuItem key={service.id} value={service.id}>
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
                      bgcolor: service.color,
                    }}
                  />
                  {service.name}
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Search button */}
        <Button
          variant="contained"
          onClick={handleSearch}
          disabled={disabled || loading || !query.trim()}
          startIcon={
            loading ? (
              <CircularProgress size={16} color="inherit" />
            ) : (
              <SearchIcon />
            )
          }
          sx={{ minWidth: 100, whiteSpace: "nowrap" }}
        >
          {loading ? "Searching..." : "Search"}
        </Button>
      </Box>

      {/* Selected services chips */}
      {selectedServices.length > 0 && (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {selectedServices.map((serviceId) => {
            const service = GROCERY_SERVICES.find((s) => s.id === serviceId);
            if (!service) return null;
            return (
              <Chip
                key={serviceId}
                label={service.name}
                size="small"
                onDelete={
                  selectedServices.length > 1
                    ? () => handleRemoveService(serviceId)
                    : undefined
                }
                sx={{
                  borderLeft: `3px solid ${service.color}`,
                  bgcolor: "action.hover",
                }}
              />
            );
          })}
        </Stack>
      )}
    </Box>
  );
});
