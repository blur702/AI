import { useCallback, useEffect, useMemo, useState } from "react";
import Container from "@mui/material/Container";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";
import LinearProgress from "@mui/material/LinearProgress";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import ShoppingCartIcon from "@mui/icons-material/ShoppingCart";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { usePriceComparison } from "../hooks/usePriceComparison";
import { ProductSearchBar } from "../components/ProductSearchBar";
import { ComparisonTable } from "../components/ComparisonTable";
import { BulkUploadDialog } from "../components/BulkUploadDialog";
import { ShoppingListResults } from "../components/ShoppingListResults";
import { SavedSelectionsPanel } from "../components/SavedSelectionsPanel";
import { StatisticsPanel } from "../components/StatisticsPanel";

export default function PriceComparisonPage() {
  const {
    comparisonResult,
    loading,
    error,
    progress,
    savedSelections,
    savedAggregation,
    searchProducts,
    saveSelection,
    deleteSelection,
    getSavedSelections,
    clearResults,
  } = usePriceComparison();

  const [activeTab, setActiveTab] = useState<number>(0);
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: "success" | "error" | "info";
  }>({
    open: false,
    message: "",
    severity: "info",
  });
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [completedListId, setCompletedListId] = useState<string | null>(null);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(true);

  // Fetch real session token from dashboard backend
  useEffect(() => {
    const fetchSessionToken = async () => {
      try {
        const response = await fetch("/api/auth/token");
        if (response.ok) {
          const data = await response.json();
          if (data.token) {
            setSessionToken(data.token);
            localStorage.setItem("price_comparison_session_token", data.token);
          }
        } else {
          // Fallback to localStorage if not authenticated
          const storedToken = localStorage.getItem("price_comparison_session_token");
          if (storedToken) {
            setSessionToken(storedToken);
          }
        }
      } catch {
        // Fallback to localStorage on error
        const storedToken = localStorage.getItem("price_comparison_session_token");
        if (storedToken) {
          setSessionToken(storedToken);
        }
      } finally {
        setTokenLoading(false);
      }
    };

    fetchSessionToken();
  }, []);

  // Load saved selections when token is available
  useEffect(() => {
    if (sessionToken && !tokenLoading) {
      getSavedSelections(sessionToken);
    }
  }, [sessionToken, tokenLoading, getSavedSelections]);

  const handleSearch = useCallback(
    async (query: string, location: string, services: string[]) => {
      clearResults();
      const result = await searchProducts(query, location, services);
      if (result) {
        setSnackbar({
          open: true,
          message: `Found ${result.groups.reduce((acc, g) => acc + g.products.length, 0)} products in ${result.groups.length} groups`,
          severity: "success",
        });
const handleSearch = useCallback(
async (query: string, location: string, services: string[]) => {
clearResults();
const { result, error: searchError } = await searchProducts(query, location, services);
if (result && !searchError) {
setSnackbar({
const handleSearch = useCallback(
async (query: string, location: string, services: string[]) => {
clearResults();
const { result, error: searchError } = await searchProducts(query, location, services);
if (result && !searchError) {
setSnackbar({
open: true,
message: `Found ${result.groups.reduce((acc, g) => acc + g.products.length, 0)} products in ${result.groups.length} groups`,
severity: "success",
});
} else {
setSnackbar({
open: true,
message: searchError || "Search failed",
severity: "error",
});
}
},
[searchProducts, clearResults]
);
async (query: string, location: string, services: string[]) => {
clearResults();
const { result, error: searchError } = await searchProducts(query, location, services);
if (result && !searchError) {
setSnackbar({
open: true,
message: `Found ${result.groups.reduce((acc, g) => acc + g.products.length, 0)} products in ${result.groups.length} groups`,
severity: "success",
});
} else {
setSnackbar({
open: true,
message: searchError || "Search failed",
severity: "error",
});
}
},
[searchProducts, clearResults]
);
async (query: string, location: string, services: string[]) => {
clearResults();
const { result, error: searchError } = await searchProducts(query, location, services);
if (result && !searchError) {
setSnackbar({
open: true,
message: `Found ${result.groups.reduce((acc, g) => acc + g.products.length, 0)} products in ${result.groups.length} groups`,
severity: "success",
});
} else {
setSnackbar({
open: true,
message: searchError || "Search failed",
severity: "error",
});
}
},
[searchProducts, clearResults]
);
message: `Found ${result.groups.reduce((acc, g) => acc + g.products.length, 0)} products in ${result.groups.length} groups`,
severity: "success",
});
} else {
setSnackbar({
open: true,
message: searchError || "Search failed",
severity: "error",
});
}
},
[searchProducts, clearResults]
);
    },
    [searchProducts, clearResults, error]
  );

  const handleSaveProduct = useCallback(
    async (productId: string) => {
      if (!sessionToken) {
        setSnackbar({
          open: true,
          message: "Please log in to save products",
          severity: "error",
        });
        return;
      }
      const success = await saveSelection(sessionToken, productId);
      setSnackbar({
        open: true,
        message: success ? "Product saved!" : "Failed to save product",
        severity: success ? "success" : "error",
      });
    },
    [saveSelection, sessionToken]
  );

  const handleDeleteSelection = useCallback(
    async (selectionId: string) => {
      if (!sessionToken) {
        setSnackbar({
          open: true,
          message: "Please log in to manage selections",
          severity: "error",
        });
        return;
      }
      const success = await deleteSelection(selectionId, sessionToken);
      setSnackbar({
        open: true,
        message: success ? "Selection removed" : "Failed to remove selection",
        severity: success ? "success" : "error",
      });
    },
    [deleteSelection, sessionToken]
  );

  const handleBulkUploadComplete = useCallback((listId: string) => {
    setUploadDialogOpen(false);
    setCompletedListId(listId);
    setActiveTab(3); // Switch to the new Shopping List tab
    setSnackbar({
      open: true,
      message: "Shopping list processed successfully!",
      severity: "success",
    });
  }, []);

  const handleBackFromResults = useCallback(() => {
    setCompletedListId(null);
    setActiveTab(0);
  }, []);

  const totalProducts = useMemo(() => {
    if (!comparisonResult) return 0;
    return comparisonResult.groups.reduce((acc, g) => acc + g.products.length, 0);
  }, [comparisonResult]);

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Page Header */}
      <Box sx={{ mb: 4, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Box>
          <Typography
            variant="h4"
            gutterBottom
            sx={{ display: "flex", alignItems: "center", gap: 1 }}
          >
            <ShoppingCartIcon /> Price Comparison
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Compare grocery prices across Amazon Fresh, Instacart, DoorDash, and
            Safeway.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<UploadFileIcon />}
          onClick={() => setUploadDialogOpen(true)}
        >
          Upload List
        </Button>
      </Box>

      {/* Search Bar */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <ProductSearchBar onSearch={handleSearch} loading={loading} />
        </CardContent>
      </Card>

      {/* Progress Indicator */}
      {(loading || progress) && (
        <Box sx={{ mb: 3 }}>
          <LinearProgress
            variant={progress ? "determinate" : "indeterminate"}
            value={
              progress && progress.total > 0
                ? (progress.current / progress.total) * 100
                : undefined
            }
          />
          {progress && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
              {progress.message || `Scraping ${progress.service}...`}
            </Typography>
          )}
        </Box>
      )}

      {/* Error Alert */}
      {error && !loading && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Content Tabs */}
      <Box sx={{ mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, v) => setActiveTab(v)}
          sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}
        >
          <Tab label="Search Results" />
          <Tab label="Saved Selections" />
          <Tab label="Statistics" />
          <Tab label="Shopping List" disabled={!completedListId} />
        </Tabs>

        {/* Search Results Tab */}
        {activeTab === 0 && (
          <>
            {!comparisonResult && !loading ? (
              <Box
                sx={{
                  textAlign: "center",
                  py: 8,
                  px: 2,
                  bgcolor: "action.hover",
                  borderRadius: 2,
                }}
              >
                <ShoppingCartIcon
                  sx={{ fontSize: 48, color: "text.secondary", mb: 2 }}
                />
                <Typography variant="h6" color="text.secondary" gutterBottom>
                  Start by searching for a product
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Enter a product name like "milk", "bread", or "eggs" to
                  compare prices across grocery services.
                </Typography>
              </Box>
            ) : (
              <>
                {comparisonResult?.llm_analysis && (
                  <Card sx={{ mb: 3, bgcolor: "primary.dark" }}>
                    <CardContent>
                      <Typography
                        variant="subtitle2"
                        sx={{ mb: 1, fontWeight: 600 }}
                      >
                        AI Analysis
                      </Typography>
                      <Typography variant="body2">
                        {comparisonResult.llm_analysis}
                      </Typography>
                      {comparisonResult.model_used && (
                        <Chip
                          label={`Model: ${comparisonResult.model_used}`}
                          size="small"
                          sx={{ mt: 1 }}
<Button
variant="outlined"
startIcon={<UploadFileIcon />}
onClick={() => setUploadDialogOpen(true)}
disabled={!sessionToken || tokenLoading}
>
Upload List
</Button>
// And/or add a guard in the dialog:
<BulkUploadDialog
open={uploadDialogOpen}
onClose={() => setUploadDialogOpen(false)}
onComplete={handleBulkUploadComplete}
sessionToken={sessionToken ?? ""}
/>
                      )}
                    </CardContent>
                  </Card>
                )}

                <ComparisonTable
                  groups={comparisonResult?.groups || []}
                  onSaveProduct={handleSaveProduct}
                  loading={loading}
                  servicesScraped={comparisonResult?.services_scraped}
                  totalProducts={totalProducts}
                />
              </>
            )}
          </>
        )}

        {/* Saved Selections Tab */}
        {activeTab === 1 && (
          <SavedSelectionsPanel
            selections={savedSelections}
            aggregation={savedAggregation}
            onDelete={handleDeleteSelection}
            loading={loading}
          />
        )}

        {/* Statistics Tab */}
        {activeTab === 2 && (
          <StatisticsPanel
            comparisonResult={comparisonResult}
            loading={loading}
          />
        )}

        {/* Shopping List Tab */}
        {activeTab === 3 && completedListId && (
          <ShoppingListResults
            listId={completedListId}
            onBack={handleBackFromResults}
          />
        )}
      </Box>

      {/* Bulk Upload Dialog */}
<Button
variant="outlined"
startIcon={<UploadFileIcon />}
onClick={() => setUploadDialogOpen(true)}
disabled={!sessionToken || tokenLoading}
>
Upload List
</Button>
// And/or add a guard in the dialog:
<BulkUploadDialog
open={uploadDialogOpen}
onClose={() => setUploadDialogOpen(false)}
onComplete={handleBulkUploadComplete}
sessionToken={sessionToken ?? ""}
/>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          severity={snackbar.severity}
          sx={{ width: "100%" }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
}
