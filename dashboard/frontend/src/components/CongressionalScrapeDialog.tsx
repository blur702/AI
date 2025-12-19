import { useEffect, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { CongressionalScrapeConfig } from "../types";

interface CongressionalScrapeDialogProps {
  open: boolean;
  onClose: () => void;
  onStart: (config: CongressionalScrapeConfig) => Promise<boolean>;
}

export function CongressionalScrapeDialog({
  open,
  onClose,
  onStart,
}: CongressionalScrapeDialogProps) {
  const [maxMembers, setMaxMembers] = useState<string>("");
  const [maxPages, setMaxPages] = useState<string>("5");
  const [dryRun, setDryRun] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setMaxMembers("");
      setMaxPages("5");
      setDryRun(false);
      setError(null);
    }
  }, [open]);

  const validate = (): boolean => {
    if (maxMembers && Number.isNaN(Number(maxMembers))) {
      setError("Max members must be a number");
      return false;
    }
    if (maxPages && (Number.isNaN(Number(maxPages)) || Number(maxPages) <= 0)) {
      setError("Max pages per member must be a positive number");
      return false;
    }
    setError(null);
    return true;
  };

  const handleStart = async () => {
    if (!validate()) return;
    const config: CongressionalScrapeConfig = {};
    if (maxMembers) config.max_members = Number(maxMembers);
    if (maxPages) config.max_pages_per_member = Number(maxPages);
    config.dry_run = dryRun;
    const ok = await onStart(config);
    if (ok) {
      onClose();
    } else {
      setError("Failed to start scraping. Please try again.");
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Start Congressional Scraping</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Configure how many members and pages to scrape. Use dry run to preview
          without writing to the database.
        </Typography>
        <TextField
          label="Max members"
          type="number"
          fullWidth
          margin="normal"
          value={maxMembers}
          onChange={(e) => setMaxMembers(e.target.value)}
          helperText="Optional. Limit the number of members to scrape."
        />
        <TextField
          label="Max pages per member"
          type="number"
          fullWidth
          margin="normal"
          value={maxPages}
          onChange={(e) => setMaxPages(e.target.value)}
          helperText="Number of pages to scrape per member (default 5)."
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
          }
          label="Dry run (do not persist data)"
        />
        {error && (
          <Typography variant="body2" color="error" sx={{ mt: 1 }}>
            {error}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleStart} variant="contained">
          Start Scraping
        </Button>
      </DialogActions>
    </Dialog>
  );
}
