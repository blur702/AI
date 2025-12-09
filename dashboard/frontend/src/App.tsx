import { useState, useCallback } from 'react';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Drawer from '@mui/material/Drawer';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import IconButton from '@mui/material/IconButton';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import MenuIcon from '@mui/icons-material/Menu';
import DashboardIcon from '@mui/icons-material/Dashboard';
import ImageIcon from '@mui/icons-material/Image';
import MusicNoteIcon from '@mui/icons-material/MusicNote';
import SettingsIcon from '@mui/icons-material/Settings';
import ComputerIcon from '@mui/icons-material/Computer';
import { ServiceCard } from './components/ServiceCard';
import { ConnectionStatus } from './components/ConnectionStatus';
import { HealthStatus } from './components/HealthStatus';
import { ResourceManager } from './components/ResourceManager';
import { SettingsPanel } from './components/SettingsPanel';
import { ThemeToggle } from './components/ThemeToggle';
import { useSocket } from './hooks/useSocket';
import { SERVICES_CONFIG, getApiBase } from './config/services';
import './App.css';

const DRAWER_WIDTH = 240;

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'main', label: 'Main Services', icon: <DashboardIcon /> },
  { id: 'image', label: 'Image Generation', icon: <ImageIcon /> },
  { id: 'music', label: 'Music Generation', icon: <MusicNoteIcon /> },
  { id: 'settings', label: 'Settings', icon: <SettingsIcon /> },
];

function App() {
  const { connected, services, startService, stopService } = useSocket();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileOpen, setMobileOpen] = useState(false);

  const mainServices = SERVICES_CONFIG.filter(s => s.section === 'main');
  const imageServices = SERVICES_CONFIG.filter(s => s.section === 'image');
  const musicServices = SERVICES_CONFIG.filter(s => s.section === 'music');

  const serverIp = window.location.hostname || '10.0.0.138';

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
    if (isMobile) {
      setMobileOpen(false);
    }
  };

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

  const drawerContent = (
    <Box sx={{ overflow: 'auto' }}>
      <Box sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
        <ComputerIcon color="primary" />
        <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
          {serverIp}
        </Typography>
      </Box>
      <List>
        {NAV_ITEMS.map((item) => (
          <ListItem key={item.id} disablePadding>
            <ListItemButton onClick={() => scrollToSection(item.id)}>
              <ListItemIcon sx={{ color: 'primary.main' }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      {/* AppBar */}
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
        }}
        elevation={0}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography
            variant="h6"
            noWrap
            component="div"
            sx={{
              flexGrow: 1,
              background: 'linear-gradient(90deg, var(--mui-palette-primary-main), var(--mui-palette-secondary-main))',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              fontWeight: 600,
            }}
          >
            AI Services Dashboard
          </Typography>
          <HealthStatus />
          <Box sx={{ ml: 1 }}>
            <ThemeToggle />
          </Box>
        </Toolbar>
      </AppBar>

      {/* Sidebar Drawer */}
      <Box
        component="nav"
        sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}
      >
        {/* Mobile drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: DRAWER_WIDTH,
              bgcolor: 'background.paper',
            },
          }}
        >
          {drawerContent}
        </Drawer>
        {/* Desktop drawer */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: DRAWER_WIDTH,
              bgcolor: 'background.paper',
              borderRight: 1,
              borderColor: 'divider',
            },
          }}
          open
        >
          {drawerContent}
        </Drawer>
      </Box>

      {/* Main Content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          mt: '64px', // AppBar height
          minHeight: 'calc(100vh - 64px)',
        }}
      >
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

        {/* Connection Status */}
        <ConnectionStatus connected={connected} />
      </Box>
    </Box>
  );
}

export default App;
