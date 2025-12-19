import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TextField from "@mui/material/TextField";
import Autocomplete from "@mui/material/Autocomplete";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

export interface CongressionalFilterState {
  member_name?: string;
  party?: string;
  state?: string;
  topic?: string;
  date_from?: string;
  date_to?: string;
}

interface CongressionalFiltersProps {
  members: string[];
  onFilterChange: (filters: CongressionalFilterState) => void;
  initialFilters?: CongressionalFilterState;
}

const US_STATES = [
  "AL",
  "AK",
  "AZ",
  "AR",
  "CA",
  "CO",
  "CT",
  "DE",
  "FL",
  "GA",
  "HI",
  "ID",
  "IL",
  "IN",
  "IA",
  "KS",
  "KY",
  "LA",
  "ME",
  "MD",
  "MA",
  "MI",
  "MN",
  "MS",
  "MO",
  "MT",
  "NE",
  "NV",
  "NH",
  "NJ",
  "NM",
  "NY",
  "NC",
  "ND",
  "OH",
  "OK",
  "OR",
  "PA",
  "RI",
  "SC",
  "SD",
  "TN",
  "TX",
  "UT",
  "VT",
  "VA",
  "WA",
  "WV",
  "WI",
  "WY",
  "DC",
];

export function CongressionalFilters({
  members,
  onFilterChange,
  initialFilters,
}: CongressionalFiltersProps) {
  const [filters, setFilters] = useState<CongressionalFilterState>(
    initialFilters || {},
  );

  useEffect(() => {
    setFilters(initialFilters || {});
  }, [initialFilters]);

  useEffect(() => {
    onFilterChange(filters);
  }, [filters, onFilterChange]);

  const memberOptions = useMemo(
    () => Array.from(new Set(members)).sort(),
    [members],
  );

  const handleClear = () => {
    setFilters({});
  };

  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">Filters</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Autocomplete
            options={memberOptions}
            value={filters.member_name || null}
            onChange={(_, value) =>
              setFilters((prev) => ({
                ...prev,
                member_name: value || undefined,
              }))
            }
            renderInput={(params) => (
              <TextField
                {...params}
                label="Member"
                placeholder="Search member by name"
                size="small"
              />
            )}
          />

          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
            <FormControl sx={{ minWidth: 160 }} size="small">
              <InputLabel id="party-label">Party</InputLabel>
              <Select
                labelId="party-label"
                label="Party"
                value={filters.party || ""}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    party: e.target.value || undefined,
                  }))
                }
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="Democrat">Democrat</MenuItem>
                <MenuItem value="Republican">Republican</MenuItem>
                <MenuItem value="Independent">Independent</MenuItem>
              </Select>
            </FormControl>

            <FormControl sx={{ minWidth: 120 }} size="small">
              <InputLabel id="state-label">State</InputLabel>
              <Select
                labelId="state-label"
                label="State"
                value={filters.state || ""}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    state: e.target.value || undefined,
                  }))
                }
              >
                <MenuItem value="">All</MenuItem>
                {US_STATES.map((st) => (
                  <MenuItem key={st} value={st}>
                    {st}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl sx={{ minWidth: 160 }} size="small">
              <InputLabel id="topic-label">Topic</InputLabel>
              <Select
                labelId="topic-label"
                label="Topic"
                value={filters.topic || ""}
                onChange={(e) =>
                  setFilters((prev) => ({
                    ...prev,
                    topic: e.target.value || undefined,
                  }))
                }
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="votes">Roll Call Votes</MenuItem>
                <MenuItem value="news">News</MenuItem>
                <MenuItem value="press">Press Releases</MenuItem>
                <MenuItem value="issues">Issues</MenuItem>
                <MenuItem value="services">Services</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
            <TextField
              label="From"
              type="date"
              size="small"
              InputLabelProps={{ shrink: true }}
              value={filters.date_from || ""}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  date_from: e.target.value || undefined,
                }))
              }
            />
            <TextField
              label="To"
              type="date"
              size="small"
              InputLabelProps={{ shrink: true }}
              value={filters.date_to || ""}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  date_to: e.target.value || undefined,
                }))
              }
            />
          </Box>

          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1 }}>
            <Button variant="outlined" size="small" onClick={handleClear}>
              Clear Filters
            </Button>
          </Box>
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
