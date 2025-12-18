import { useState } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Drawer from '@mui/material/Drawer';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
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
import MemoryIcon from '@mui/icons-material/Memory';
import ComputerIcon from '@mui/icons-material/Computer';
import { ConnectionStatus } from './components/ConnectionStatus';
import { HealthStatus } from './components/HealthStatus';
import { ThemeToggle } from './components/ThemeToggle';
import { useSocket } from './hooks/useSocket';
import DashboardHome from './pages/DashboardHome';
import ModelsPage from './pages/ModelsPage';
import CongressionalDataPage from './pages/CongressionalDataPage';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import './App.css';

const DRAWER_WIDTH = 240;

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  path: string;
  isSection?: boolean; // For scroll-to-section navigation on dashboard
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { id: 'models', label: 'Models', icon: <MemoryIcon />, path: '/models' },
  { id: 'congressional', label: 'Congressional Data', icon: <AccountBalanceIcon />, path: '/congressional' },
  { id: 'main', label: 'Main Services', icon: <DashboardIcon />, path: '/', isSection: true },
  { id: 'image', label: 'Image Generation', icon: <ImageIcon />, path: '/', isSection: true },
  { id: 'music', label: 'Music Generation', icon: <MusicNoteIcon />, path: '/', isSection: true },
  { id: 'settings', label: 'Settings', icon: <SettingsIcon />, path: '/', isSection: true },
];

function App() {
  const { connected } = useSocket();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const serverIp = window.location.hostname || 'localhost';

  const handleDrawerToggle = (): void => {
    setMobileOpen(!mobileOpen);
  };

  const handleNavClick = (item: NavItem): void => {
    if (item.isSection) {
      // If we're not on the dashboard, navigate there first
      if (location.pathname !== '/') {
        navigate('/');
        // Use setTimeout to wait for navigation before scrolling
        setTimeout(() => {
          const element = document.getElementById(item.id);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth' });
          }
        }, 100);
      } else {
        const element = document.getElementById(item.id);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth' });
        }
      }
    } else {
      navigate(item.path);
    }
    if (isMobile) {
      setMobileOpen(false);
    }
  };

  const isActiveRoute = (item: NavItem): boolean => {
    if (item.isSection) return false;
    return location.pathname === item.path;
  };

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
            <ListItemButton
              onClick={() => handleNavClick(item)}
              selected={isActiveRoute(item)}
              sx={{
                pl: item.isSection ? 4 : 2, // Indent section items
                '&.Mui-selected': {
                  bgcolor: 'action.selected',
                  '&:hover': {
                    bgcolor: 'action.selected',
                  },
                },
              }}
            >
              <ListItemIcon sx={{ color: isActiveRoute(item) ? 'primary.main' : 'text.secondary', minWidth: 40 }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.label}
                primaryTypographyProps={{
                  fontSize: item.isSection ? '0.875rem' : '1rem',
                  color: item.isSection ? 'text.secondary' : 'text.primary',
                }}
              />
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
        <Routes>
          <Route path="/" element={<DashboardHome />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/congressional" element={<CongressionalDataPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        {/* Connection Status */}
        <ConnectionStatus connected={connected} />
      </Box>
    </Box>
  );
}

export default App;
