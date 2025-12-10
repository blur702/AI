import { useCallback, memo } from 'react';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import { ServiceCard } from '../components/ServiceCard';
import { ResourceManager } from '../components/ResourceManager';
import { SettingsPanel } from '../components/SettingsPanel';
import { useSocket } from '../hooks/useSocket';
import { SERVICES_CONFIG, getApiBase } from '../config/services';

const DashboardHome = memo(function DashboardHome() {
  const { services, startService, stopService } = useSocket();

  const mainServices = SERVICES_CONFIG.filter(s => s.section === 'main');
  const imageServices = SERVICES_CONFIG.filter(s => s.section === 'image');
  const musicServices = SERVICES_CONFIG.filter(s => s.section === 'music');

  const handlePauseService = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${getApiBase()}/api/services/${id}/pause`, {
        method: 'POST',
      });
      if (!response.ok) {
        console.error('Failed to pause service:', await response.text());
      }
    } catch (err) {
      console.error('Error pausing service:', err);
    }
  }, []);

  const handleResumeService = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${getApiBase()}/api/services/${id}/resume`, {
        method: 'POST',
      });
      if (!response.ok) {
        console.error('Failed to resume service:', await response.text());
      }
    } catch (err) {
      console.error('Error resuming service:', err);
    }
  }, []);

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Resource Manager */}
      <ResourceManager />

      {/* Settings Panel */}
      <Box id="settings">
        <SettingsPanel />
      </Box>

      {/* Main Services Grid */}
      <Box id="main" sx={{ mb: 4, scrollMarginTop: '80px' }}>
        <Typography variant="h5" color="text.secondary" sx={{ mb: 3 }}>
          Main Services
        </Typography>
        <Grid container spacing={3}>
          {mainServices.map(config => (
            <Grid item xs={12} sm={6} lg={4} key={config.id}>
              <ServiceCard
                config={config}
                state={services[config.id]}
                onStart={startService}
                onStop={stopService}
                onPause={handlePauseService}
                onResume={handleResumeService}
              />
            </Grid>
          ))}
        </Grid>
      </Box>

      {/* Image Generation Section */}
      <Box id="image" sx={{ mb: 4, scrollMarginTop: '80px' }}>
        <Typography variant="h5" color="text.secondary" sx={{ mb: 3 }}>
          Image Generation
        </Typography>
        <Grid container spacing={3}>
          {imageServices.map(config => (
            <Grid item xs={12} sm={6} lg={4} key={config.id}>
              <ServiceCard
                config={config}
                state={services[config.id]}
                onStart={startService}
                onStop={stopService}
                onPause={handlePauseService}
                onResume={handleResumeService}
              />
            </Grid>
          ))}
        </Grid>
      </Box>

      {/* Music Generation Section */}
      <Box id="music" sx={{ mb: 4, scrollMarginTop: '80px' }}>
        <Typography variant="h5" color="text.secondary" sx={{ mb: 3 }}>
          Music Generation
        </Typography>
        <Grid container spacing={3}>
          {musicServices.map(config => (
            <Grid item xs={12} sm={6} lg={4} key={config.id}>
              <ServiceCard
                config={config}
                state={services[config.id]}
                onStart={startService}
                onStop={stopService}
                onPause={handlePauseService}
                onResume={handleResumeService}
              />
            </Grid>
          ))}
        </Grid>
      </Box>

      {/* Footer */}
      <Box sx={{ textAlign: 'center', mt: 6 }}>
        <Typography variant="body2" color="text.secondary">
          RTX 3090 (24GB) - Ryzen 9 5900X - 64GB RAM
        </Typography>
      </Box>
    </Container>
  );
});

export default DashboardHome;
