import { useState, useCallback, memo } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import LinearProgress from '@mui/material/LinearProgress';
import Stepper from '@mui/material/Stepper';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Divider from '@mui/material/Divider';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SettingsIcon from '@mui/icons-material/Settings';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import StopIcon from '@mui/icons-material/Stop';
import DeleteIcon from '@mui/icons-material/Delete';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import { useIngestion } from '../hooks/useIngestion';
import { IngestionRequest, CleanCollectionsRequest } from '../types';

const CODE_SERVICES = [
  { value: 'all', label: 'All AI Services' },
  { value: 'core', label: 'Core Project' },
  { value: 'alltalk', label: 'AllTalk TTS' },
  { value: 'audiocraft', label: 'AudioCraft' },
  { value: 'comfyui', label: 'ComfyUI' },
  { value: 'diffrhythm', label: 'DiffRhythm' },
  { value: 'musicgpt', label: 'MusicGPT' },
  { value: 'stable_audio', label: 'Stable Audio' },
  { value: 'wan2gp', label: 'Wan2GP' },
  { value: 'yue', label: 'YuE' },
];

const MDN_SECTIONS = [
  { value: '', label: 'All sections' },
  { value: 'css', label: 'CSS only' },
  { value: 'html', label: 'HTML only' },
  { value: 'webapi', label: 'Web APIs only' },
];

const INGESTION_STEPS = [
  { key: 'documentation', label: 'Docs' },
  { key: 'code', label: 'Code' },
  { key: 'drupal', label: 'Drupal' },
  { key: 'mdn_javascript', label: 'MDN JS' },
  { key: 'mdn_webapis', label: 'MDN Web' },
];

const COLLECTION_OPTIONS = [
  { value: 'documentation', label: 'Documentation' },
  { value: 'code_entity', label: 'Code Entities' },
  { value: 'drupal_api', label: 'Drupal API' },
  { value: 'mdn_javascript', label: 'MDN JavaScript' },
  { value: 'mdn_webapis', label: 'MDN Web APIs' },
];

type IngestionType = 'documentation' | 'code' | 'drupal' | 'mdn_javascript' | 'mdn_webapis';
type CollectionType = 'documentation' | 'code_entity' | 'drupal_api' | 'mdn_javascript' | 'mdn_webapis';

export const SettingsPanel = memo(function SettingsPanel() {
  const {
    status,
    progress,
    lastResult,
    error,
    loading,
    startIngestion,
    cancelIngestion,
    pauseIngestion,
    resumeIngestion,
    cleanCollections,
    reindexCollections,
  } = useIngestion();

  const [expanded, setExpanded] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<Set<IngestionType>>(
    new Set(['documentation', 'code'])
  );
  const [codeService, setCodeService] = useState('all');
  const [reindex, setReindex] = useState(false);
  const [drupalLimit, setDrupalLimit] = useState<number | null>(null);
  const [mdnLimit, setMdnLimit] = useState<number | null>(100);
  const [mdnSection, setMdnSection] = useState<string>('');

  // Dialog states
  const [cleanDialogOpen, setCleanDialogOpen] = useState(false);
  const [reindexDialogOpen, setReindexDialogOpen] = useState(false);
  const [selectedCollections, setSelectedCollections] = useState<Set<CollectionType>>(new Set());
  const [isCleanLoading, setIsCleanLoading] = useState(false);

  const handleTypeToggle = useCallback((type: IngestionType) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleCollectionToggle = useCallback((collection: CollectionType) => {
    setSelectedCollections(prev => {
      const next = new Set(prev);
      if (next.has(collection)) {
        next.delete(collection);
      } else {
        next.add(collection);
      }
      return next;
    });
  }, []);

  const handleStart = useCallback(async () => {
    if (selectedTypes.size === 0) return;

    const hasMdn = selectedTypes.has('mdn_javascript') || selectedTypes.has('mdn_webapis');
    const request: IngestionRequest = {
      types: Array.from(selectedTypes),
      reindex,
      code_service: codeService,
      drupal_limit: selectedTypes.has('drupal') ? drupalLimit : undefined,
      mdn_limit: hasMdn ? mdnLimit : undefined,
      mdn_section: selectedTypes.has('mdn_webapis') && mdnSection ? mdnSection : undefined,
    };

    await startIngestion(request);
  }, [selectedTypes, reindex, codeService, drupalLimit, mdnLimit, mdnSection, startIngestion]);

  const handleClean = useCallback(async () => {
    if (selectedCollections.size === 0) return;

    setIsCleanLoading(true);
    const request: CleanCollectionsRequest = {
      collections: Array.from(selectedCollections),
    };

    const success = await cleanCollections(request);
    setIsCleanLoading(false);

    if (success) {
      setCleanDialogOpen(false);
      setSelectedCollections(new Set());
    }
  }, [selectedCollections, cleanCollections]);

  const handleReindex = useCallback(async () => {
    if (selectedTypes.size === 0) return;

    const hasMdn = selectedTypes.has('mdn_javascript') || selectedTypes.has('mdn_webapis');
    const request: IngestionRequest = {
      types: Array.from(selectedTypes),
      reindex: true, // Always true for reindex
      code_service: codeService,
      drupal_limit: selectedTypes.has('drupal') ? drupalLimit : undefined,
      mdn_limit: hasMdn ? mdnLimit : undefined,
      mdn_section: selectedTypes.has('mdn_webapis') && mdnSection ? mdnSection : undefined,
    };

    await reindexCollections(request);
    setReindexDialogOpen(false);
  }, [selectedTypes, codeService, drupalLimit, mdnLimit, mdnSection, reindexCollections]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 3 }}>
        <CircularProgress size={24} sx={{ mr: 2 }} />
        <Typography color="text.secondary">Loading settings...</Typography>
      </Box>
    );
  }

  const isRunning = status?.is_running ?? false;
  const isPaused = status?.paused ?? false;
  const docCount = status?.collections?.documentation?.object_count ?? 0;
  const codeCount = status?.collections?.code_entity?.object_count ?? 0;
  const drupalCount = status?.collections?.drupal_api?.object_count ?? 0;
  const mdnJsCount = status?.collections?.mdn_javascript?.object_count ?? 0;
  const mdnWebCount = status?.collections?.mdn_webapis?.object_count ?? 0;

  // Calculate progress percentage
  let progressPercent = 0;
  if (progress && progress.total > 0) {
    progressPercent = (progress.current / progress.total) * 100;
  }

  // Determine active step for Stepper
  const getActiveStep = () => {
    if (!progress) return -1;
    return INGESTION_STEPS.findIndex(step => step.key === progress.type);
  };

  // Get status chip props - shows status for running, paused, completed, and failed states
  const getStatusChip = () => {
    // Running states take priority
    if (isRunning) {
      if (isPaused) {
        return <Chip icon={<PauseIcon />} label="Paused" color="warning" size="small" />;
      }
      return <Chip icon={<CircularProgress size={12} />} label="Running" color="primary" size="small" />;
    }

    // Show error state
    if (error) {
      return <Chip icon={<ErrorIcon />} label="Failed" color="error" size="small" />;
    }

    // Show completed state from last result
    if (lastResult) {
      if (lastResult.success) {
        return <Chip icon={<CheckCircleIcon />} label="Completed" color="success" size="small" />;
      }
      return <Chip icon={<ErrorIcon />} label="Failed" color="error" size="small" />;
    }

    // No active state
    return null;
  };

  return (
    <>
      <Accordion
        expanded={expanded}
        onChange={(_, isExpanded) => setExpanded(isExpanded)}
        sx={{
          bgcolor: 'background.paper',
          borderRadius: '12px !important',
          border: 1,
          borderColor: 'divider',
          '&:before': { display: 'none' },
          mb: 3,
        }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Chip
              icon={<SettingsIcon />}
              label="Settings"
              size="small"
              sx={{
                background: 'linear-gradient(135deg, var(--mui-palette-primary-main), var(--mui-palette-secondary-main))',
                color: 'white',
                fontWeight: 600,
                '& .MuiChip-icon': { color: 'white' },
              }}
            />
            {getStatusChip()}
          </Box>
        </AccordionSummary>

        <AccordionDetails>
          {/* Collection Statistics */}
          <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2, mb: 3 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Weaviate Collections
            </Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 1 }}>
              <Typography variant="body2">Documentation: <strong>{docCount.toLocaleString()}</strong></Typography>
              <Typography variant="body2">Code: <strong>{codeCount.toLocaleString()}</strong></Typography>
              <Typography variant="body2">Drupal: <strong>{drupalCount.toLocaleString()}</strong></Typography>
              <Typography variant="body2">MDN JS: <strong>{mdnJsCount.toLocaleString()}</strong></Typography>
              <Typography variant="body2">MDN Web: <strong>{mdnWebCount.toLocaleString()}</strong></Typography>
            </Box>
          </Box>

          <Divider sx={{ my: 2 }} />

          {/* Ingestion Type Selection */}
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            Select Data Sources
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 2 }}>
            {(['documentation', 'code', 'drupal', 'mdn_javascript', 'mdn_webapis'] as IngestionType[]).map(type => (
              <FormControlLabel
                key={type}
                control={
                  <Checkbox
                    checked={selectedTypes.has(type)}
                    onChange={() => handleTypeToggle(type)}
                    disabled={isRunning}
                    size="small"
                  />
                }
                label={
                  type === 'documentation' ? 'Documentation (Markdown)' :
                  type === 'code' ? 'Code Entities' :
                  type === 'drupal' ? 'Drupal API (Web Scrape)' :
                  type === 'mdn_javascript' ? 'MDN JavaScript' :
                  'MDN Web APIs (CSS/HTML/WebAPI)'
                }
                sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.875rem' } }}
              />
            ))}
          </Box>

          {/* Code Service Selector */}
          {selectedTypes.has('code') && (
            <FormControl size="small" sx={{ minWidth: 200, mb: 2 }} disabled={isRunning}>
              <InputLabel>Code scope</InputLabel>
              <Select value={codeService} label="Code scope" onChange={(e) => setCodeService(e.target.value)}>
                {CODE_SERVICES.map(({ value, label }) => (
                  <MenuItem key={value} value={value}>{label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {/* Drupal Limit */}
          {selectedTypes.has('drupal') && (
            <FormControl size="small" sx={{ minWidth: 200, mb: 2 }} disabled={isRunning}>
              <InputLabel>Drupal limit</InputLabel>
              <Select
                value={drupalLimit ?? 'unlimited'}
                label="Drupal limit"
                onChange={(e) => setDrupalLimit(e.target.value === 'unlimited' ? null : parseInt(e.target.value as string))}
              >
                <MenuItem value="unlimited">Unlimited</MenuItem>
                <MenuItem value="100">100 entities</MenuItem>
                <MenuItem value="500">500 entities</MenuItem>
                <MenuItem value="1000">1,000 entities</MenuItem>
              </Select>
            </FormControl>
          )}

          {/* MDN Limit */}
          {(selectedTypes.has('mdn_javascript') || selectedTypes.has('mdn_webapis')) && (
            <FormControl size="small" sx={{ minWidth: 200, mb: 2 }} disabled={isRunning}>
              <InputLabel>MDN limit</InputLabel>
              <Select
                value={mdnLimit ?? 'unlimited'}
                label="MDN limit"
                onChange={(e) => setMdnLimit(e.target.value === 'unlimited' ? null : parseInt(e.target.value as string))}
              >
                <MenuItem value="50">50 docs</MenuItem>
                <MenuItem value="100">100 docs</MenuItem>
                <MenuItem value="250">250 docs</MenuItem>
                <MenuItem value="unlimited">Unlimited</MenuItem>
              </Select>
            </FormControl>
          )}

          {/* MDN Section */}
          {selectedTypes.has('mdn_webapis') && (
            <FormControl size="small" sx={{ minWidth: 200, mb: 2, ml: 2 }} disabled={isRunning}>
              <InputLabel>Section</InputLabel>
              <Select value={mdnSection} label="Section" onChange={(e) => setMdnSection(e.target.value)}>
                {MDN_SECTIONS.map(({ value, label }) => (
                  <MenuItem key={value} value={value}>{label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {/* Reindex Checkbox */}
          <FormControlLabel
            control={
              <Checkbox
                checked={reindex}
                onChange={(e) => setReindex(e.target.checked)}
                disabled={isRunning}
                size="small"
                color="warning"
              />
            }
            label="Delete existing data before indexing"
            sx={{ mb: 2, '& .MuiFormControlLabel-label': { fontSize: '0.875rem', color: 'warning.main' } }}
          />

          {/* Action Buttons */}
          <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
            {!isRunning ? (
              <>
                <Button
                  variant="contained"
                  color="success"
                  startIcon={<PlayArrowIcon />}
                  onClick={handleStart}
                  disabled={selectedTypes.size === 0}
                >
                  Start
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<DeleteIcon />}
                  onClick={() => setCleanDialogOpen(true)}
                >
                  Clean
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<RefreshIcon />}
                  onClick={() => setReindexDialogOpen(true)}
                  disabled={selectedTypes.size === 0}
                >
                  Reindex
                </Button>
              </>
            ) : (
              <>
                {!isPaused ? (
                  <Button
                    variant="contained"
                    color="warning"
                    startIcon={<PauseIcon />}
                    onClick={pauseIngestion}
                  >
                    Pause
                  </Button>
                ) : (
                  <Button
                    variant="contained"
                    color="success"
                    startIcon={<PlayArrowIcon />}
                    onClick={resumeIngestion}
                  >
                    Resume
                  </Button>
                )}
                <Button
                  variant="contained"
                  color="error"
                  startIcon={<StopIcon />}
                  onClick={cancelIngestion}
                >
                  Cancel
                </Button>
              </>
            )}
          </Box>

          {/* Progress Stepper */}
          {isRunning && (
            <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2, mb: 2 }}>
              <Stepper activeStep={getActiveStep()} alternativeLabel>
                {INGESTION_STEPS.map((step, index) => (
                  <Step key={step.key} completed={index < getActiveStep()}>
                    <StepLabel
                      StepIconProps={{
                        icon: index < getActiveStep() ? <CheckCircleIcon color="success" /> :
                              index === getActiveStep() && !isPaused ? <CircularProgress size={20} /> :
                              index === getActiveStep() && isPaused ? <PauseIcon color="warning" /> :
                              undefined
                      }}
                    >
                      {step.label}
                    </StepLabel>
                  </Step>
                ))}
              </Stepper>

              {/* Progress Bar */}
              {progress && (
                <Box sx={{ mt: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      {progress.phase}: {progress.message}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {progress.current} / {progress.total}
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={progressPercent}
                    color={isPaused ? 'warning' : 'primary'}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              )}
            </Box>
          )}

          {/* Error Display */}
          {error && (
            <Alert severity="error" icon={<ErrorIcon />} sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {/* Result Display */}
          {lastResult && !isRunning && (
            <Alert
              severity={lastResult.success ? 'success' : 'error'}
              icon={lastResult.success ? <CheckCircleIcon /> : <ErrorIcon />}
            >
              <Typography variant="subtitle2">
                {lastResult.success ? 'Indexing Complete' : 'Indexing Failed'}
              </Typography>
              <Typography variant="body2">
                Duration: {lastResult.duration_seconds.toFixed(1)}s
                {lastResult.stats.documentation && ` | Docs: ${lastResult.stats.documentation.chunks} chunks`}
                {lastResult.stats.code && ` | Code: ${lastResult.stats.code.entities} entities`}
                {lastResult.stats.drupal && ` | Drupal: ${lastResult.stats.drupal.entities_inserted} entities`}
                {lastResult.stats.mdn_javascript && ` | MDN JS: ${lastResult.stats.mdn_javascript.entities_inserted} entities`}
                {lastResult.stats.mdn_webapis && ` | MDN Web APIs: ${lastResult.stats.mdn_webapis.entities_inserted} entities`}
              </Typography>
            </Alert>
          )}
        </AccordionDetails>
      </Accordion>

      {/* Clean Dialog */}
      <Dialog open={cleanDialogOpen} onClose={() => setCleanDialogOpen(false)}>
        <DialogTitle>Clean Collections</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Select collections to delete. This action cannot be undone.
          </Typography>
          {COLLECTION_OPTIONS.map(({ value, label }) => (
            <FormControlLabel
              key={value}
              control={
                <Checkbox
                  checked={selectedCollections.has(value as CollectionType)}
                  onChange={() => handleCollectionToggle(value as CollectionType)}
                />
              }
              label={label}
              sx={{ display: 'block' }}
            />
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCleanDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleClean}
            color="error"
            variant="contained"
            disabled={selectedCollections.size === 0 || isCleanLoading}
            startIcon={isCleanLoading ? <CircularProgress size={16} /> : <DeleteIcon />}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reindex Dialog */}
      <Dialog open={reindexDialogOpen} onClose={() => setReindexDialogOpen(false)}>
        <DialogTitle>Force Reindex</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            This will delete existing data and re-index the selected sources.
            Selected types: {Array.from(selectedTypes).join(', ')}
          </Typography>
          <Alert severity="warning" sx={{ mt: 1 }}>
            All existing data in the selected collections will be deleted.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReindexDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleReindex}
            color="warning"
            variant="contained"
            startIcon={<RefreshIcon />}
          >
            Start Reindex
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
});
