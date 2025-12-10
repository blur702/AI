import { useState, useMemo, memo } from 'react';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActions from '@mui/material/CardActions';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import Alert from '@mui/material/Alert';
import Snackbar from '@mui/material/Snackbar';
import Skeleton from '@mui/material/Skeleton';
import Tooltip from '@mui/material/Tooltip';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Collapse from '@mui/material/Collapse';
import SearchIcon from '@mui/icons-material/Search';
import MemoryIcon from '@mui/icons-material/Memory';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import DownloadIcon from '@mui/icons-material/Download';
import DeleteIcon from '@mui/icons-material/Delete';
import InfoIcon from '@mui/icons-material/Info';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import HelpIcon from '@mui/icons-material/Help';
import { useModels } from '../hooks/useModels';
import type { OllamaModelDetailed } from '../types';

type FilterType = 'all' | 'loaded' | 'available' | 'downloading';
type SortType = 'name' | 'size' | 'parameters' | 'vram';

const ModelsPage = memo(function ModelsPage() {
  const {
    models,
    loadedModels,
    downloadingModels,
    loadingModels,
    gpuInfo,
    loading,
    error,
    totalCount,
    loadedCount,
    refresh,
    loadModel,
    unloadModel,
    downloadModel,
    removeModel,
  } = useModels({ pollingInterval: 10000 });

  // UI State
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<FilterType>('all');
  const [sortBy, setSortBy] = useState<SortType>('name');
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());

  // Dialog State
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false);
  const [downloadModelName, setDownloadModelName] = useState('');
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false);
  const [modelToRemove, setModelToRemove] = useState<string | null>(null);
  const [infoDialogOpen, setInfoDialogOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<OllamaModelDetailed | null>(null);
  const [helpDialogOpen, setHelpDialogOpen] = useState(false);

  // Loading State
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  // Notification State
  const [notification, setNotification] = useState<{ open: boolean; message: string; severity: 'success' | 'error' | 'info' }>({
    open: false,
    message: '',
    severity: 'info',
  });

  // Filter and sort models
  const filteredModels = useMemo(() => {
    let result = [...models];

    // Apply search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(m =>
        m.name.toLowerCase().includes(query) ||
        m.family.toLowerCase().includes(query) ||
        m.capability_description.toLowerCase().includes(query)
      );
    }

    // Apply type filter
    switch (filter) {
      case 'loaded':
        result = result.filter(m => m.is_loaded);
        break;
      case 'available':
        result = result.filter(m => !m.is_loaded);
        break;
      case 'downloading':
        result = result.filter(m => downloadingModels[m.name]);
        break;
    }

    // Apply sort
    result.sort((a, b) => {
      switch (sortBy) {
        case 'size':
          return b.size_gb - a.size_gb;
        case 'parameters': {
          // Parse numeric portion for proper sorting (e.g., "7B" -> 7, "70B" -> 70)
          const parseParams = (p: string) => {
            const match = p.match(/^(\d+(?:\.\d+)?)/);
            return match ? parseFloat(match[1]) : 0;
          };
          return parseParams(b.parameters || '') - parseParams(a.parameters || '');
        }
        case 'vram':
          return b.estimated_vram_mb - a.estimated_vram_mb;
        default:
          return a.name.localeCompare(b.name);
      }
    });

    return result;
  }, [models, searchQuery, filter, sortBy, downloadingModels]);

  // Calculate VRAM usage
  const vramUsage = useMemo(() => {
    if (!gpuInfo) return null;

    const loadedVram = loadedModels.reduce((sum, m) => sum + m.estimated_vram_mb, 0);
    const usedPercent = (gpuInfo.used_mb / gpuInfo.total_mb) * 100;

    return {
      total: gpuInfo.total_mb,
      used: gpuInfo.used_mb,
      free: gpuInfo.free_mb,
      loadedEstimate: loadedVram,
      percent: usedPercent,
      status: usedPercent < 50 ? 'success' : usedPercent < 80 ? 'warning' : 'error',
    };
  }, [gpuInfo, loadedModels]);

  // Handlers
  const handleLoadModel = async (modelName: string, expectedVramMb?: number) => {
    const result = await loadModel(modelName, expectedVramMb);

    if (!result.success) {
      setNotification({
        open: true,
        message: result.message,
        severity: 'error',
      });
    }
    // Success notification will come when WebSocket reports completion
  };

  const handleUnloadModel = async (modelName: string, expectedVramMb?: number) => {
    const result = await unloadModel(modelName, expectedVramMb);

    if (!result.success) {
      setNotification({
        open: true,
        message: result.message,
        severity: 'error',
      });
    }
    // Success notification will come when WebSocket reports completion
  };

  const handleDownloadModel = async () => {
    if (!downloadModelName.trim()) return;

    const modelName = downloadModelName.trim();
    setDownloadDialogOpen(false);
    const result = await downloadModel(modelName);
    setDownloadModelName('');

    setNotification({
      open: true,
      message: result.success ? `Download started for "${modelName}"` : result.message,
      severity: result.success ? 'info' : 'error',
    });
  };

  const handleRemoveModel = async () => {
    if (!modelToRemove) return;

    const modelName = modelToRemove;
    setRemoveDialogOpen(false);
    setActionLoading(prev => ({ ...prev, [modelName]: true }));
    const result = await removeModel(modelName);
    setActionLoading(prev => ({ ...prev, [modelName]: false }));
    setModelToRemove(null);

    setNotification({
      open: true,
      message: result.success ? `Model "${modelName}" removed successfully` : result.message,
      severity: result.success ? 'success' : 'error',
    });
  };

  const handleShowInfo = (model: OllamaModelDetailed) => {
    setSelectedModel(model);
    setInfoDialogOpen(true);
  };

  const toggleExpanded = (modelName: string) => {
    setExpandedCards(prev => {
      const next = new Set(prev);
      if (next.has(modelName)) {
        next.delete(modelName);
      } else {
        next.add(modelName);
      }
      return next;
    });
  };

  const getStatusColor = (model: OllamaModelDetailed) => {
    const loadProgress = loadingModels[model.name];
    if (loadProgress) {
      return loadProgress.action === 'load' ? 'info' : 'warning';
    }
    if (downloadingModels[model.name]) return 'warning';
    if (model.is_loaded) return 'success';
    return 'default';
  };

  const getStatusLabel = (model: OllamaModelDetailed) => {
    const loadProgress = loadingModels[model.name];
    if (loadProgress) {
      const action = loadProgress.action === 'load' ? 'Loading' : 'Unloading';
      return `${action} ${loadProgress.progress}%`;
    }
    if (downloadingModels[model.name]) return 'Downloading';
    if (model.is_loaded) return 'Loaded';
    return 'Available';
  };

  const formatSize = (mb: number) => {
    if (mb >= 1024) {
      return `${(mb / 1024).toFixed(1)} GB`;
    }
    return `${mb} MB`;
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <MemoryIcon /> Ollama Models
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {totalCount} models available, {loadedCount} loaded
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Download new model">
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={() => setDownloadDialogOpen(true)}
            >
              Download
            </Button>
          </Tooltip>
          <Tooltip title="Refresh models">
            <IconButton onClick={refresh} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Help">
            <IconButton onClick={() => setHelpDialogOpen(true)}>
              <HelpIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* VRAM Summary Card */}
      {vramUsage && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              GPU VRAM Usage
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">
                  {formatSize(vramUsage.used)} / {formatSize(vramUsage.total)}
                </Typography>
                <Typography variant="body2" color={`${vramUsage.status}.main`}>
                  {vramUsage.percent.toFixed(1)}%
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={vramUsage.percent}
                color={vramUsage.status as 'success' | 'warning' | 'error'}
                sx={{ height: 10, borderRadius: 1 }}
              />
            </Box>
            <Typography variant="body2" color="text.secondary">
              Estimated loaded models VRAM: ~{formatSize(vramUsage.loadedEstimate)}
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Search and Filter Controls */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          placeholder="Search models..."
          size="small"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ minWidth: 250 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />

        <ToggleButtonGroup
          value={filter}
          exclusive
          onChange={(_, value) => value && setFilter(value)}
          size="small"
        >
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="loaded">Loaded</ToggleButton>
          <ToggleButton value="available">Available</ToggleButton>
        </ToggleButtonGroup>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Sort by</InputLabel>
          <Select
            value={sortBy}
            label="Sort by"
            onChange={(e) => setSortBy(e.target.value as SortType)}
          >
            <MenuItem value="name">Name</MenuItem>
            <MenuItem value="size">Size</MenuItem>
            <MenuItem value="parameters">Parameters</MenuItem>
            <MenuItem value="vram">VRAM Est.</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* Models Grid */}
      {loading && models.length === 0 ? (
        <Grid container spacing={3}>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Grid item xs={12} sm={6} md={4} key={i}>
              <Card>
                <CardContent>
                  <Skeleton variant="text" width="60%" height={32} />
                  <Skeleton variant="text" width="40%" />
                  <Skeleton variant="rectangular" height={60} sx={{ mt: 2 }} />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <Grid container spacing={3}>
          {filteredModels.map((model) => (
            <Grid item xs={12} sm={6} md={4} key={model.name}>
              <Card
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  borderLeft: 4,
                  borderColor: loadingModels[model.name]
                    ? (loadingModels[model.name].action === 'load' ? 'info.main' : 'warning.main')
                    : model.is_loaded ? 'success.main' : downloadingModels[model.name] ? 'warning.main' : 'grey.300',
                  opacity: actionLoading[model.name] ? 0.7 : 1,
                  transition: 'opacity 0.2s',
                }}
              >
                <CardContent sx={{ flexGrow: 1 }}>
                  {/* Header */}
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                    <Typography variant="h6" component="div" sx={{ wordBreak: 'break-word', pr: 1 }}>
                      {model.name}
                    </Typography>
                    <Chip
                      label={getStatusLabel(model)}
                      size="small"
                      color={getStatusColor(model)}
                    />
                  </Box>

                  {/* Family Badge */}
                  <Chip
                    label={model.family}
                    size="small"
                    variant="outlined"
                    sx={{ mb: 1 }}
                  />

                  {/* Model Stats */}
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {model.parameters && `${model.parameters} • `}
                    {model.quantization && `${model.quantization} • `}
                    {model.size}
                  </Typography>

                  {/* VRAM Estimate */}
                  {model.estimated_vram_mb > 0 && (
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="body2" color="text.secondary">
                        Est. VRAM: ~{formatSize(model.estimated_vram_mb)}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={vramUsage ? Math.min((model.estimated_vram_mb / vramUsage.total) * 100, 100) : 0}
                        sx={{ height: 4, borderRadius: 1, mt: 0.5 }}
                      />
                    </Box>
                  )}

                  {/* Download Progress */}
                  {downloadingModels[model.name] && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="body2" color="warning.main">
                        {downloadingModels[model.name].progress}
                      </Typography>
                      <LinearProgress color="warning" sx={{ mt: 0.5 }} />
                    </Box>
                  )}

                  {/* Load/Unload Progress */}
                  {loadingModels[model.name] && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="body2" color={loadingModels[model.name].action === 'load' ? 'info.main' : 'warning.main'}>
                        {loadingModels[model.name].action === 'load' ? 'Loading' : 'Unloading'} model...
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={loadingModels[model.name].progress}
                        color={loadingModels[model.name].action === 'load' ? 'info' : 'warning'}
                        sx={{ mt: 0.5, height: 6, borderRadius: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                        {loadingModels[model.name].progress}% complete
                      </Typography>
                    </Box>
                  )}

                  {/* Expandable Description */}
                  <Box sx={{ mt: 1 }}>
                    <Button
                      size="small"
                      onClick={() => toggleExpanded(model.name)}
                      endIcon={expandedCards.has(model.name) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      sx={{ textTransform: 'none', p: 0 }}
                    >
                      {expandedCards.has(model.name) ? 'Less' : 'More'}
                    </Button>
                    <Collapse in={expandedCards.has(model.name)}>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        {model.capability_description || 'No description available.'}
                      </Typography>
                    </Collapse>
                  </Box>
                </CardContent>

                <CardActions sx={{ justifyContent: 'flex-end', px: 2, pb: 2 }}>
                  <Tooltip title="Model info">
                    <IconButton size="small" onClick={() => handleShowInfo(model)}>
                      <InfoIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>

                  {model.is_loaded ? (
                    <Tooltip title="Unload model">
                      <IconButton
                        size="small"
                        color="warning"
                        onClick={() => handleUnloadModel(model.name, model.estimated_vram_mb)}
                        disabled={actionLoading[model.name] || !!loadingModels[model.name]}
                      >
                        <StopIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  ) : (
                    <Tooltip title="Load model">
                      <IconButton
                        size="small"
                        color="success"
                        onClick={() => handleLoadModel(model.name, model.estimated_vram_mb)}
                        disabled={actionLoading[model.name] || !!downloadingModels[model.name] || !!loadingModels[model.name]}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}

                  <Tooltip title="Remove model">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        setModelToRemove(model.name);
                        setRemoveDialogOpen(true);
                      }}
                      disabled={actionLoading[model.name] || model.is_loaded || !!loadingModels[model.name]}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Empty State */}
      {!loading && filteredModels.length === 0 && (
        <Box sx={{ textAlign: 'center', py: 8 }}>
          <MemoryIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h6" color="text.secondary">
            {searchQuery || filter !== 'all'
              ? 'No models match your filters'
              : 'No models found'}
          </Typography>
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={() => setDownloadDialogOpen(true)}
            sx={{ mt: 2 }}
          >
            Download a Model
          </Button>
        </Box>
      )}

      {/* Download Dialog */}
      <Dialog open={downloadDialogOpen} onClose={() => setDownloadDialogOpen(false)}>
        <DialogTitle>Download Model</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Enter the model name to download from Ollama. Examples: llama3.2, qwen2.5:32b, mistral:7b-instruct
          </DialogContentText>
          <TextField
            autoFocus
            fullWidth
            label="Model name"
            placeholder="e.g., llama3.2:latest"
            value={downloadModelName}
            onChange={(e) => setDownloadModelName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDownloadModel()}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDownloadDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleDownloadModel} variant="contained" disabled={!downloadModelName.trim()}>
            Download
          </Button>
        </DialogActions>
      </Dialog>

      {/* Remove Confirmation Dialog */}
      <Dialog open={removeDialogOpen} onClose={() => setRemoveDialogOpen(false)}>
        <DialogTitle>Remove Model</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to remove "{modelToRemove}"? This will delete the model from disk and cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoveDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleRemoveModel} color="error" variant="contained">
            Remove
          </Button>
        </DialogActions>
      </Dialog>

      {/* Model Info Dialog */}
      <Dialog open={infoDialogOpen} onClose={() => setInfoDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{selectedModel?.name ?? 'Model Info'}</DialogTitle>
        <DialogContent>
          {selectedModel && (
            <Box>
              <Typography variant="subtitle2" color="text.secondary">Family</Typography>
              <Typography gutterBottom>{selectedModel.family}</Typography>

              <Typography variant="subtitle2" color="text.secondary">Parameters</Typography>
              <Typography gutterBottom>{selectedModel.parameters || 'N/A'}</Typography>

              <Typography variant="subtitle2" color="text.secondary">Quantization</Typography>
              <Typography gutterBottom>{selectedModel.quantization || 'N/A'}</Typography>

              <Typography variant="subtitle2" color="text.secondary">Size</Typography>
              <Typography gutterBottom>{selectedModel.size} ({selectedModel.size_gb.toFixed(2)} GB)</Typography>

              <Typography variant="subtitle2" color="text.secondary">Format</Typography>
              <Typography gutterBottom>{selectedModel.format || 'N/A'}</Typography>

              <Typography variant="subtitle2" color="text.secondary">Estimated VRAM</Typography>
              <Typography gutterBottom>~{formatSize(selectedModel.estimated_vram_mb)}</Typography>

              <Typography variant="subtitle2" color="text.secondary">Description</Typography>
              <Typography>{selectedModel.capability_description || 'No description available.'}</Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInfoDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Help Dialog */}
      <Dialog open={helpDialogOpen} onClose={() => setHelpDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Model Management Help</DialogTitle>
        <DialogContent>
          <Typography variant="subtitle2" gutterBottom>Loading/Unloading Models</Typography>
          <Typography variant="body2" paragraph>
            Loading a model puts it into GPU VRAM for fast inference. Unloading removes it from VRAM but keeps it on disk. Only loaded models can be used for generation.
          </Typography>

          <Typography variant="subtitle2" gutterBottom>VRAM Management</Typography>
          <Typography variant="body2" paragraph>
            Each model requires VRAM when loaded. Monitor the VRAM usage bar at the top. If you run out of VRAM, unload models you're not using.
          </Typography>

          <Typography variant="subtitle2" gutterBottom>Model Names</Typography>
          <Typography variant="body2" paragraph>
            Models use the format "name:tag" (e.g., "llama3.2:latest"). Common tags include version numbers, sizes (7b, 13b, 70b), and variants (instruct, chat).
          </Typography>

          <Typography variant="subtitle2" gutterBottom>Quantization</Typography>
          <Typography variant="body2" paragraph>
            Quantization reduces model size and VRAM usage. Q4 is smallest/fastest, Q8 is larger/more accurate, FP16 is full precision. Most models use Q4_K_M for good balance.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Notification Snackbar */}
      <Snackbar
        open={notification.open}
        autoHideDuration={5000}
        onClose={() => setNotification(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity={notification.severity}
          onClose={() => setNotification(prev => ({ ...prev, open: false }))}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Container>
  );
});

export default ModelsPage;
