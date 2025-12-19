import { memo, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import Button from "@mui/material/Button";
import AppsIcon from "@mui/icons-material/Apps";
import AccountBalanceIcon from "@mui/icons-material/AccountBalance";
import { getApiBase } from "../config/services";

const AppsPage = memo(function AppsPage() {
  const navigate = useNavigate();
  const [congressionalCount, setCongressionalCount] = useState<number | null>(
    null,
  );

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${getApiBase()}/api/congressional/status`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (!data) return;
        const objCount =
          data.collections?.congressional_data?.object_count ?? null;
        if (typeof objCount === "number") {
          setCongressionalCount(objCount);
        }
      })
      .catch(() => {});

    return () => controller.abort();
  }, []);

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h4"
          gutterBottom
          sx={{ display: "flex", alignItems: "center", gap: 1 }}
        >
          <AppsIcon /> Apps
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Custom-built applications for specialized tasks.
        </Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box
                sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}
              >
                <AccountBalanceIcon color="primary" />
                <Typography variant="h6">Congressional Data</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Search and analyze congressional member website content with
                rich filters and analytics.
              </Typography>
              {congressionalCount !== null && (
                <Typography variant="caption" color="text.secondary">
                  Indexed documents: {congressionalCount}
                </Typography>
              )}
            </CardContent>
            <CardActions>
              <Button
                size="small"
                variant="contained"
                onClick={() => navigate("/apps/congressional")}
              >
                Open
              </Button>
            </CardActions>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
});

export default AppsPage;
