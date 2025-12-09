import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActions from '@mui/material/CardActions';
import Box from '@mui/material/Box';
import Avatar from '@mui/material/Avatar';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Collapse from '@mui/material/Collapse';
import CircularProgress from '@mui/material/CircularProgress';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import StopIcon from '@mui/icons-material/Stop';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { ServiceConfig, ServiceState, ServiceStatus } from '../types';
import { getServiceUrl } from '../config/services';
import './ServiceCard.css';

interface ServiceCardProps {
  config: ServiceConfig;
  state?: ServiceState;
  onStart: (id: string) => void;
  onStop: (id: string) => void;
  onPause?: (id: string) => void;
  onResume?: (id: string) => void;
}

export function ServiceCard({ config, state, onStart, onStop, onPause, onResume }: ServiceCardProps) {
  const status: ServiceStatus = state?.status || 'stopped';
  const isRunning = status === 'running';
  const isPaused = status === 'paused';
  const isStarting = status === 'starting';
  const isStopping = status === 'stopping';
  const isError = status === 'error';
  const isExternal = config.external;
  const canManage = !isExternal && state?.manageable !== false;

  const handleOpen = () => {
    if (isRunning) {
      window.open(getServiceUrl(config.port, config.proxyId), '_blank');
    }
  };

  const getStatusColor = (): 'success' | 'warning' | 'default' | 'error' => {
    switch (status) {
      case 'running': return 'success';
      case 'paused':
      case 'starting':
      case 'stopping': return 'warning';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  const getStatusLabel = (): string => {
    switch (status) {
      case 'running': return 'Running';
      case 'paused': return 'Paused';
      case 'starting': return 'Starting';
      case 'stopping': return 'Stopping';
      case 'error': return 'Error';
      default: return 'Stopped';
    }
  };

  return (
    <Card
      className={config.cardClass}
      elevation={2}
      sx={{
        position: 'relative',
        transition: 'all 0.3s ease',
        opacity: status === 'stopped' ? 0.7 : 1,
        borderLeft: isRunning ? '3px solid' : 'none',
        borderColor: isRunning ? 'success.main' : 'transparent',
        '&:hover': {
          transform: 'translateY(-5px)',
          boxShadow: 6,
        },
      }}
    >
      <CardContent>
        {/* Header with Icon and Title */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <Avatar
            className="card-icon"
            sx={{
              width: 50,
              height: 50,
              borderRadius: '12px',
              fontSize: '1.5rem',
            }}
          >
            {config.icon}
          </Avatar>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" component="div" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
              {config.name}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
              <Chip
                size="small"
                color={getStatusColor()}
                label={getStatusLabel()}
                sx={{ height: 20, fontSize: '0.7rem' }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                Port {config.port}
              </Typography>
            </Box>
          </Box>
        </Box>

        {/* Description */}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2, lineHeight: 1.6 }}>
          {config.description}
        </Typography>

        {/* Instructions (shown when running) */}
        <Collapse in={isRunning && !!config.instructions}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1,
              p: 1.5,
              mb: 2,
              borderRadius: 1,
              bgcolor: 'action.hover',
              border: '1px solid',
              borderColor: 'primary.main',
            }}
          >
            <InfoOutlinedIcon sx={{ color: 'primary.main', fontSize: '1.1rem', mt: 0.2 }} />
            <Typography variant="body2" sx={{ color: 'primary.light', fontSize: '0.85rem' }}>
              {config.instructions}
            </Typography>
          </Box>
        </Collapse>

        {/* Tags */}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
          {config.tags.map(tag => (
            <Chip
              key={tag}
              label={tag}
              size="small"
              variant="outlined"
              sx={{
                fontSize: '0.75rem',
                height: 24,
                borderColor: 'divider',
                color: 'text.secondary',
              }}
            />
          ))}
        </Stack>
      </CardContent>

      <CardActions sx={{ px: 2, pb: 2, pt: 0, justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {canManage && (
            <>
              {!isRunning && !isPaused && !isStopping && (
                <Button
                  variant="contained"
                  color="success"
                  size="small"
                  startIcon={isStarting ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
                  onClick={() => onStart(config.id)}
                  disabled={isStarting}
                >
                  {isStarting ? 'Starting...' : 'Start'}
                </Button>
              )}
              {isRunning && onPause && (
                <Tooltip title="Pause service">
                  <IconButton
                    size="small"
                    onClick={() => onPause(config.id)}
                    sx={{ color: 'warning.main' }}
                    aria-label="Pause service"
                  >
                    <PauseIcon />
                  </IconButton>
                </Tooltip>
              )}
              {isPaused && onResume && (
                <Tooltip title="Resume service">
                  <IconButton
                    size="small"
                    onClick={() => onResume(config.id)}
                    sx={{ color: 'success.main' }}
                    aria-label="Resume service"
                  >
                    <PlayArrowIcon />
                  </IconButton>
                </Tooltip>
              )}
              {(isRunning || isPaused || isStopping) && (
                <Button
                  variant="contained"
                  color="error"
                  size="small"
                  startIcon={isStopping ? <CircularProgress size={16} color="inherit" /> : <StopIcon />}
                  onClick={() => onStop(config.id)}
                  disabled={isStopping}
                >
                  {isStopping ? 'Stopping...' : 'Stop'}
                </Button>
              )}
            </>
          )}
        </Box>
        <Tooltip title={isRunning ? 'Open in new tab' : 'Service not running'}>
          <span>
            <IconButton
              size="small"
              onClick={handleOpen}
              disabled={!isRunning}
              aria-label="Open service in new tab"
              sx={{
                color: isRunning ? 'primary.main' : 'action.disabled',
                '&:hover': {
                  bgcolor: 'action.hover',
                },
              }}
            >
              <OpenInNewIcon />
            </IconButton>
          </span>
        </Tooltip>
      </CardActions>

      {/* Loading/Error Overlay */}
      {(isStarting || isStopping || isError) && (
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: 'rgba(0, 0, 0, 0.85)',
            borderRadius: 1,
            zIndex: 10,
          }}
        >
          {!isError && <CircularProgress size={40} sx={{ mb: 2 }} />}
          <Typography variant="body2" color="text.primary">
            {isStarting && 'Starting service...'}
            {isStopping && 'Stopping service...'}
            {isError && (state?.error || 'Error')}
          </Typography>
        </Box>
      )}
    </Card>
  );
}
