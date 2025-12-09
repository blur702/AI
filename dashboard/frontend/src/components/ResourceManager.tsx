import { useState, useEffect, useCallback } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import IconButton from '@mui/material/IconButton';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CloseIcon from '@mui/icons-material/Close';
import MemoryIcon from '@mui/icons-material/Memory';
import { ResourceSummary, ResourceSettings, OllamaModel, GpuProcess } from '../types';
import { getApiBase } from '../config/services';

interface ResourceManagerProps {
  onUnloadModel?: (modelName: string) => void;
}

function formatBytes(mb: number): string {
  if (mb >= 1024) {
    return `${(mb / 1024).toFixed(1)} GB`;
  }
  return `${mb} MB`;
}

function formatIdleTime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return 'N/A';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

function getVramColor(percent: number): 'success' | 'warning' | 'error' {
  if (percent > 80) return 'error';
  if (percent > 50) return 'warning';
  return 'success';
}

export function ResourceManager({ onUnloadModel }: ResourceManagerProps) {
  const [summary, setSummary] = useState<ResourceSummary | null>(null);
  const [settings, setSettings] = useState<ResourceSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, settingsRes] = await Promise.all([
        fetch(`${getApiBase()}/api/resources/summary`),
        fetch(`${getApiBase()}/api/resources/settings`)
      ]);

      if (!summaryRes.ok) {
        const errorText = await summaryRes.text();
        throw new Error(`Failed to fetch summary (${summaryRes.status}): ${errorText}`);
      }

      if (!settingsRes.ok) {
        const errorText = await settingsRes.text();
        throw new Error(`Failed to fetch settings (${settingsRes.status}): ${errorText}`);
      }

      const summaryData = await summaryRes.json();
      const settingsData = await settingsRes.json();

      setSummary(summaryData);
      setSettings(settingsData);
    } catch (error) {
      console.error('Error fetching resource data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleToggleAutoStop = async () => {
    if (!settings) return;

    try {
      const response = await fetch(`${getApiBase()}/api/resources/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_stop_enabled: !settings.auto_stop_enabled })
      });
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error('Error updating settings:', error);
    }
  };

  const handleTimeoutChange = async (minutes: number) => {
    try {
      const response = await fetch(`${getApiBase()}/api/resources/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idle_timeout_minutes: minutes })
      });
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error('Error updating settings:', error);
    }
  };

  const handleUnloadOllamaModel = async (modelName: string) => {
    try {
      const response = await fetch(`${getApiBase()}/api/models/ollama/unload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName })
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`Failed to unload model "${modelName}" (${response.status}): ${errorText}`);
        throw new Error(`Failed to unload model: ${response.status} ${response.statusText}`);
      }

      fetchData();
      onUnloadModel?.(modelName);
    } catch (error) {
      console.error('Error unloading model:', error);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 3 }}>
        <CircularProgress size={24} sx={{ mr: 2 }} />
        <Typography color="text.secondary">Loading resource info...</Typography>
      </Box>
    );
  }

  const gpu = summary?.gpu ?? null;
  const usedPercent = gpu && gpu.total_mb > 0 ? (gpu.used_mb / gpu.total_mb) * 100 : 0;

  return (
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
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{
          '&:hover': { bgcolor: 'action.hover' },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%', pr: 2 }}>
          <Chip
            icon={<MemoryIcon />}
            label="GPU"
            size="small"
            sx={{
              background: 'linear-gradient(135deg, var(--mui-palette-primary-main), var(--mui-palette-secondary-main))',
              color: 'white',
              fontWeight: 600,
              '& .MuiChip-icon': { color: 'white' },
            }}
          />
          {gpu && (
            <Box sx={{ flexGrow: 1, maxWidth: 150 }}>
              <LinearProgress
                variant="determinate"
                value={usedPercent}
                color={getVramColor(usedPercent)}
                sx={{
                  height: 8,
                  borderRadius: 4,
                  bgcolor: 'action.disabledBackground',
                }}
              />
            </Box>
          )}
          <Typography variant="body2" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
            {gpu ? `${formatBytes(gpu.used_mb)} / ${formatBytes(gpu.total_mb)}` : 'N/A'}
          </Typography>
        </Box>
      </AccordionSummary>

      <AccordionDetails sx={{ pt: 0 }}>
        {/* GPU Info Section */}
        {gpu && (
          <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2, mb: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              GPU: {gpu.name}
            </Typography>
            <Box sx={{ position: 'relative', mb: 1.5 }}>
              <LinearProgress
                variant="determinate"
                value={usedPercent}
                color={getVramColor(usedPercent)}
                sx={{
                  height: 24,
                  borderRadius: 1.5,
                  bgcolor: 'action.disabledBackground',
                }}
              />
              <Typography
                variant="body2"
                sx={{
                  position: 'absolute',
                  right: 10,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  fontWeight: 600,
                  color: 'common.white',
                  textShadow: '0 1px 2px rgba(0,0,0,0.5)',
                }}
              >
                {usedPercent.toFixed(1)}%
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" color="text.secondary">
                Used: {formatBytes(gpu.used_mb)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Free: {formatBytes(gpu.free_mb)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Util: {gpu.utilization}%
              </Typography>
            </Box>
          </Box>
        )}

        {/* Loaded Ollama Models */}
        {summary?.ollama_models && summary.ollama_models.length > 0 && (
          <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2, mb: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Loaded LLM Models
            </Typography>
            <List dense disablePadding>
              {summary.ollama_models.map((model: OllamaModel) => (
                <ListItem
                  key={model.name}
                  sx={{
                    bgcolor: 'action.selected',
                    borderRadius: 1.5,
                    mb: 1,
                    '&:last-child': { mb: 0 },
                  }}
                  secondaryAction={
                    <IconButton
                      edge="end"
                      size="small"
                      onClick={() => handleUnloadOllamaModel(model.name)}
                      sx={{
                        bgcolor: 'error.dark',
                        color: 'error.light',
                        '&:hover': { bgcolor: 'error.main' },
                      }}
                    >
                      <CloseIcon fontSize="small" />
                    </IconButton>
                  }
                >
                  <ListItemText
                    primary={model.name}
                    secondary={model.size}
                    primaryTypographyProps={{ fontFamily: 'monospace', fontSize: '0.9rem' }}
                    secondaryTypographyProps={{ fontSize: '0.8rem' }}
                  />
                </ListItem>
              ))}
            </List>
          </Box>
        )}

        {/* GPU Processes */}
        {summary?.gpu_processes && summary.gpu_processes.length > 0 && (
          <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2, mb: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              GPU Processes
            </Typography>
            <List dense disablePadding>
              {summary.gpu_processes.map((proc: GpuProcess) => (
                <ListItem
                  key={proc.pid}
                  sx={{
                    bgcolor: 'action.selected',
                    borderRadius: 1.5,
                    mb: 1,
                    '&:last-child': { mb: 0 },
                  }}
                >
                  <ListItemText
                    primary={proc.name.split('\\').pop()}
                    secondary={proc.memory}
                    primaryTypographyProps={{ fontFamily: 'monospace', fontSize: '0.9rem' }}
                    secondaryTypographyProps={{ fontSize: '0.8rem' }}
                  />
                </ListItem>
              ))}
            </List>
          </Box>
        )}

        {/* Running Services */}
        {summary?.services && summary.services.running_services.length > 0 && (
          <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2, mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="subtitle2" color="text.secondary">
                Running Services ({summary.services.total_running})
              </Typography>
              {summary.services.gpu_intensive_running > 0 && (
                <Chip
                  label={`${summary.services.gpu_intensive_running} GPU`}
                  size="small"
                  color="secondary"
                  sx={{
                    height: 20,
                    fontSize: '0.7rem',
                  }}
                />
              )}
            </Box>
            <List dense disablePadding>
              {summary.services.running_services.map(svc => (
                <ListItem
                  key={svc.id}
                  sx={{
                    bgcolor: 'action.selected',
                    borderRadius: 1.5,
                    mb: 1,
                    borderLeft: svc.gpu_intensive ? 3 : 0,
                    borderColor: svc.gpu_intensive ? 'secondary.main' : 'transparent',
                    '&:last-child': { mb: 0 },
                  }}
                >
                  <ListItemText
                    primary={svc.name}
                    secondary={`Idle: ${formatIdleTime(svc.idle_seconds)}`}
                    primaryTypographyProps={{ fontFamily: 'monospace', fontSize: '0.9rem' }}
                    secondaryTypographyProps={{ fontSize: '0.8rem' }}
                  />
                </ListItem>
              ))}
            </List>
          </Box>
        )}

        {/* Auto-Stop Settings */}
        {settings && (
          <>
            <Divider sx={{ my: 2 }} />
            <Box sx={{ bgcolor: 'action.hover', borderRadius: 2, p: 2 }}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Auto-Stop Idle Services
              </Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={settings.auto_stop_enabled}
                    onChange={handleToggleAutoStop}
                    sx={{ color: 'primary.main' }}
                  />
                }
                label="Enable auto-stop for GPU services"
                sx={{ mb: 2, '& .MuiFormControlLabel-label': { color: 'text.secondary' } }}
              />
              <FormControl size="small" sx={{ minWidth: 150 }} disabled={!settings.auto_stop_enabled}>
                <InputLabel>Timeout</InputLabel>
                <Select
                  value={settings.idle_timeout_minutes}
                  label="Timeout"
                  onChange={(e) => handleTimeoutChange(Number(e.target.value))}
                >
                  <MenuItem value={5}>5 minutes</MenuItem>
                  <MenuItem value={15}>15 minutes</MenuItem>
                  <MenuItem value={30}>30 minutes</MenuItem>
                  <MenuItem value={60}>1 hour</MenuItem>
                  <MenuItem value={120}>2 hours</MenuItem>
                </Select>
              </FormControl>
            </Box>
          </>
        )}
      </AccordionDetails>
    </Accordion>
  );
}
