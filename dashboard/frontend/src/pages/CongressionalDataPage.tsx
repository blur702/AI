import { useMemo, useState } from 'react';
import Container from '@mui/material/Container';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardHeader from '@mui/material/CardHeader';
import CardContent from '@mui/material/CardContent';
import CardActions from '@mui/material/CardActions';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import TextField from '@mui/material/TextField';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';
import SearchIcon from '@mui/icons-material/Search';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import CircularProgress from '@mui/material/CircularProgress';
import Pagination from '@mui/material/Pagination';
import { useCongressional } from '../hooks/useCongressional';
import {
  CongressionalQueryResult,
  CongressionalStatus,
} from '../types';
import { CongressionalFilters, CongressionalFilterState } from '../components/CongressionalFilters';
import { CongressionalResultCard } from '../components/CongressionalResultCard';
import { CongressionalAnalytics } from '../components/CongressionalAnalytics';
import { CongressionalScrapeDialog } from '../components/CongressionalScrapeDialog';

function getStatusColor(status: string): 'default' | 'success' | 'warning' | 'error' {
  switch (status) {
    case 'running':
      return 'warning';
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    default:
      return 'default';
  }
}

type ChatRole = 'user' | 'assistant' | 'system';

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  meta?: CongressionalFilterState;
}

export default function CongressionalDataPage() {
  const {
    status,
    progress,
    loading,
    error,
    startScrape,
    cancelScrape,
    pauseScrape,
    resumeScrape,
    queryData,
  } = useCongressional();

  const [queryText, setQueryText] = useState<string>('');
  const [filters, setFilters] = useState<CongressionalFilterState>({});
  const [queryResults, setQueryResults] = useState<CongressionalQueryResult[]>([]);
  const [queryLoading, setQueryLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(10);
  const [totalResults, setTotalResults] = useState<number>(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' | 'info' }>({
    open: false,
    message: '',
    severity: 'info',
  });
  const [scrapeDialogOpen, setScrapeDialogOpen] = useState<boolean>(false);
  const [starting, setStarting] = useState<boolean>(false);
  const [pausing, setPausing] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);

  const collectionStats: CongressionalStatus['collections']['congressional_data'] | null = status
    ? status.collections.congressional_data
    : null;

  const memberOptions = useMemo(
    () => Object.keys(collectionStats?.member_counts || {}).sort(),
    [collectionStats],
  );

  const visibleResults = useMemo(() => {
    const start = (page - 1) * pageSize;
    const end = start + pageSize;
    return queryResults.slice(start, end);
  }, [queryResults, page, pageSize]);

  const handleStartScrape = async (config: Parameters<typeof startScrape>[0]): Promise<boolean> => {
    setStarting(true);
    try {
      const ok = await startScrape(config);
      setSnackbar({
        open: true,
        message: ok ? 'Scraping started' : 'Failed to start scraping',
        severity: ok ? 'success' : 'error',
      });
      return ok;
    } finally {
      setStarting(false);
    }
  };

  const handlePauseResume = async () => {
    if (!status) return;
    setPausing(true);
    try {
      if (status.paused) {
        const ok = await resumeScrape();
        setSnackbar({
          open: true,
          message: ok ? 'Scraping resumed' : 'Failed to resume scraping',
          severity: ok ? 'success' : 'error',
        });
      } else {
        const ok = await pauseScrape();
        setSnackbar({
          open: true,
          message: ok ? 'Scraping paused' : 'Failed to pause scraping',
          severity: ok ? 'success' : 'error',
        });
      }
    } finally {
      setPausing(false);
    }
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      const ok = await cancelScrape();
      setSnackbar({
        open: true,
        message: ok ? 'Cancellation requested' : 'Failed to cancel scraping',
        severity: ok ? 'success' : 'error',
      });
    } finally {
      setCancelling(false);
    }
  };

  const handleSearch = async () => {
    if (!queryText.trim()) {
      setSnackbar({
        open: true,
        message: 'Please enter a query',
        severity: 'info',
      });
      return;
    }
    setQueryLoading(true);

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: queryText.trim(),
      meta: filters,
    };
    setMessages((prev) => [...prev, userMessage]);

    const req = {
      query: queryText,
      member_name: filters.member_name,
      party: filters.party,
      state: filters.state,
      topic: filters.topic,
      date_from: filters.date_from,
      date_to: filters.date_to,
      limit: 50,
      messages: messages.map((m) => ({ role: m.role, content: m.content })).concat({
        role: 'user' as const,
        content: queryText.trim(),
      }),
    };

    const resp = await queryData(req);
    if (resp && resp.success) {
      setQueryResults(resp.results);
      setTotalResults(resp.total_results);
      setPage(1);
      setActiveTab(0);

      const topTitles = resp.results.slice(0, 3).map((r: CongressionalQueryResult) => `• ${r.title || r.url}`);
      const summaryLines = [
        `Found ${resp.total_results} document(s) matching your query.`,
        ...(topTitles.length ? ['Top results:', ...topTitles] : []),
      ];
      const assistant: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: summaryLines.join('\n'),
      };
      setMessages((prev) => [...prev, assistant]);
    } else if (!resp) {
      const msg = error || 'Query failed';
      const assistant: ChatMessage = {
        id: `assistant-error-${Date.now()}`,
        role: 'assistant',
        content: msg,
      };
      setMessages((prev) => [...prev, assistant]);
      setSnackbar({
        open: true,
        message: msg,
        severity: 'error',
      });
    }

    setQueryLoading(false);
  };

  const handleMemberClick = (name: string) => {
    setFilters((prev) => ({ ...prev, member_name: name }));
  };

  const currentProgressValue =
    progress && progress.total > 0 ? (progress.current / progress.total) * 100 : 0;

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h4"
          gutterBottom
          sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
        >
          <AccountBalanceIcon /> Congressional Data
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Scrape, search, and analyze content from congressional member websites.
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Scraping Controls */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Scraping Controls" />
            <CardContent>
              {loading && !status ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                  <CircularProgress size={24} />
                </Box>
              ) : (
                <>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      Status
                    </Typography>
                    <Chip
                      label={status?.status ?? 'unknown'}
                      size="small"
                      color={getStatusColor(status?.status ?? '')}
                    />
                    {status?.paused && (
                      <Chip
                        label="paused"
                        size="small"
                        sx={{ ml: 1 }}
                      />
                    )}
                  </Box>

                  {progress && progress.total > 0 && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="caption" color="text.secondary">
                        {progress.phase}: {progress.current} / {progress.total}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={currentProgressValue}
                        sx={{ mt: 0.5 }}
                      />
                    </Box>
                  )}

                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      Documents
                    </Typography>
                    <Typography variant="body2">
                      {collectionStats?.object_count ?? 0} indexed documents
                    </Typography>
                  </Box>

                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      Members
                    </Typography>
                    <Typography variant="body2">
                      {collectionStats?.member_counts
                        ? Object.keys(collectionStats.member_counts).length
                        : 0}{' '}
                      members
                    </Typography>
                  </Box>
                </>
              )}
            </CardContent>
            <CardActions>
              <Button
                variant="contained"
                size="small"
                onClick={() => setScrapeDialogOpen(true)}
                disabled={status?.status === 'running' || starting}
              >
                {starting ? <CircularProgress size={16} /> : 'Start'}
              </Button>
              <Button
                size="small"
                onClick={handlePauseResume}
                disabled={!status || status.status !== 'running' || pausing}
              >
                {pausing ? (
                  <CircularProgress size={16} />
                ) : status?.paused ? (
                  'Resume'
                ) : (
                  'Pause'
                )}
              </Button>
              <Button
                size="small"
                color="error"
                onClick={handleCancel}
                disabled={!status || status.status !== 'running' || cancelling}
              >
                {cancelling ? <CircularProgress size={16} /> : 'Cancel'}
              </Button>
            </CardActions>
          </Card>
        </Grid>

        {/* Query + Results */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader title="Query" />
            <CardContent>
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <TextField
                  fullWidth
                  size="small"
                  placeholder="Ask a question or search congressional content..."
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  InputProps={{
                    startAdornment: <SearchIcon fontSize="small" sx={{ mr: 1 }} />,
                  }}
                  disabled={queryLoading}
                />
                <Button
                  variant="contained"
                  onClick={handleSearch}
                  disabled={queryLoading}
                  startIcon={queryLoading ? <CircularProgress size={16} /> : <SearchIcon />}
                >
                  Search
                </Button>
              </Box>

              <CongressionalFilters
                members={memberOptions}
                onFilterChange={setFilters}
                initialFilters={filters}
              />
            </CardContent>
          </Card>

          <Box sx={{ mt: 3 }}>
            <Tabs
              value={activeTab}
              onChange={(_, v) => setActiveTab(v)}
              sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
            >
              <Tab label="Results" />
              <Tab label="Analytics" />
            </Tabs>

            {activeTab === 0 && (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {/* Chat transcript */}
                {messages.length > 0 && (
                  <Box sx={{ mb: 2 }}>
                    {messages.map((m) => (
                      <Box
                        key={m.id}
                        sx={{
                          mb: 1,
                          display: 'flex',
                          justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                        }}
                      >
                        <Box
                          sx={{
                            maxWidth: '80%',
                            px: 1.5,
                            py: 1,
                            borderRadius: 2,
                            bgcolor:
                              m.role === 'user'
                                ? 'primary.main'
                                : m.role === 'assistant'
                                ? 'grey.100'
                                : 'grey.200',
                            color: m.role === 'user' ? 'primary.contrastText' : 'text.primary',
                            whiteSpace: 'pre-line',
                          }}
                        >
                          {m.content}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                )}

                {/* Results list */}
                {queryResults.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No results yet. Run a search to see documents.
                  </Typography>
                ) : (
                  <>
                    {visibleResults.map((r) => (
                      <CongressionalResultCard
                        key={`${r.member_name}-${r.url}-${r.scraped_at}`}
                        result={r}
                        onMemberClick={handleMemberClick}
                      />
                    ))}
                    <Box
                      sx={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        mt: 2,
                      }}
                    >
                      <Typography variant="caption" color="text.secondary">
                        Showing{' '}
                        {queryResults.length === 0
                          ? 0
                          : (page - 1) * pageSize + 1}{' '}
                        –
                        {Math.min(page * pageSize, totalResults || queryResults.length)} of{' '}
                        {totalResults || queryResults.length}
                      </Typography>
                      <Pagination
                        count={Math.max(
                          1,
                          Math.ceil((totalResults || queryResults.length) / pageSize),
                        )}
                        page={page}
                        onChange={(_, value) => setPage(value)}
                        size="small"
                      />
                    </Box>
                  </>
                )}
              </Box>
            )}

            {activeTab === 1 && collectionStats && (
              <CongressionalAnalytics stats={collectionStats} queryResults={queryResults} />
            )}
          </Box>
        </Grid>
      </Grid>

      {error && (
        <Box sx={{ mt: 2 }}>
          <Alert severity="error">{error}</Alert>
        </Box>
      )}

      <CongressionalScrapeDialog
        open={scrapeDialogOpen}
        onClose={() => setScrapeDialogOpen(false)}
        onStart={handleStartScrape}
      />

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
      >
        <Alert
          onClose={() => setSnackbar((prev) => ({ ...prev, open: false }))}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
}
