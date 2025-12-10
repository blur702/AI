import { memo } from 'react';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import { useThemeMode } from '../theme/ThemeContext';
import './ThemeToggle.css';

export const ThemeToggle = memo(function ThemeToggle(): JSX.Element {
  const { mode, toggleTheme } = useThemeMode();

  const tooltipTitle = mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';

  return (
    <Tooltip title={tooltipTitle} arrow>
      <IconButton
        onClick={toggleTheme}
        className="theme-toggle"
        aria-label={tooltipTitle}
        sx={{
          color: 'var(--mui-palette-primary-main)',
          transition: 'transform 0.3s ease, color 0.3s ease',
          '&:hover': {
            backgroundColor: 'rgba(var(--mui-palette-primary-main-rgb), 0.1)',
          },
        }}
      >
        {mode === 'dark' ? (
          <Brightness7Icon className="theme-icon" />
        ) : (
          <Brightness4Icon className="theme-icon" />
        )}
      </IconButton>
    </Tooltip>
  );
});
