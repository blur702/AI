import { createTheme } from "@mui/material/styles";

// Palette configuration interface
interface PaletteConfig {
  mode: "light" | "dark";
  primary: { main: string; light: string; dark: string; contrastText: string };
  secondary: {
    main: string;
    light: string;
    dark: string;
    contrastText: string;
  };
  background: { default: string; paper: string; gradientStop: string };
  text: { primary: string; secondary: string };
  error: { main: string };
  warning: { main: string };
  success: { main: string };
  divider: string;
}

// Dark palette matching current aesthetic
const darkPalette: PaletteConfig = {
  mode: "dark",
  primary: {
    main: "#00d4ff",
    light: "#5ce1ff",
    dark: "#00a4cc",
    contrastText: "#000000",
  },
  secondary: {
    main: "#7b2cbf",
    light: "#a855f7",
    dark: "#5b1d8f",
    contrastText: "#ffffff",
  },
  background: {
    default: "#1a1a2e",
    paper: "#16213e",
    gradientStop: "#0f3460",
  },
  text: {
    primary: "#ffffff",
    secondary: "#aaaaaa",
  },
  error: {
    main: "#ff4444",
  },
  warning: {
    main: "#ffaa00",
  },
  success: {
    main: "#00ff88",
  },
  divider: "rgba(255, 255, 255, 0.1)",
};

// Light palette with professional colors
const lightPalette: PaletteConfig = {
  mode: "light",
  primary: {
    main: "#1976d2",
    light: "#42a5f5",
    dark: "#1565c0",
    contrastText: "#ffffff",
  },
  secondary: {
    main: "#9c27b0",
    light: "#ba68c8",
    dark: "#7b1fa2",
    contrastText: "#ffffff",
  },
  background: {
    default: "#f5f5f5",
    paper: "#ffffff",
    gradientStop: "#e0e0e0",
  },
  text: {
    primary: "#000000",
    secondary: "#666666",
  },
  error: {
    main: "#d32f2f",
  },
  warning: {
    main: "#ed6c02",
  },
  success: {
    main: "#2e7d32",
  },
  divider: "rgba(0, 0, 0, 0.12)",
};

// Helper function to convert hex to RGB (supports both 3 and 6 digit hex codes)
function hexToRgb(hex: string): string {
  // Expand shorthand form (e.g. "#03F") to full form (e.g. "#0033FF")
  const shorthandRegex = /^#?([a-f\d])([a-f\d])([a-f\d])$/i;
  const expandedHex = hex.replace(
    shorthandRegex,
    (_m, r, g, b) => r + r + g + g + b + b,
  );

  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(expandedHex);
  if (result) {
    return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
  }
  return "0, 0, 0";
}

export function createAppTheme(mode: "light" | "dark") {
  const palette = mode === "dark" ? darkPalette : lightPalette;

  return createTheme({
    palette,
    typography: {
      fontFamily:
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif",
      h1: {
        fontSize: "2.5rem",
        fontWeight: 600,
      },
      h2: {
        fontSize: "1.5rem",
        fontWeight: 500,
      },
      body1: {
        fontSize: "1rem",
      },
      body2: {
        fontSize: "0.9rem",
      },
    },
    shape: {
      borderRadius: 12,
    },
    transitions: {
      duration: {
        shortest: 150,
        shorter: 200,
        short: 250,
        standard: 300,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          ":root": {
            "--mui-palette-mode": mode,
            "--mui-palette-primary-main": palette.primary.main,
            "--mui-palette-primary-light": palette.primary.light,
            "--mui-palette-primary-dark": palette.primary.dark,
            "--mui-palette-primary-main-rgb": hexToRgb(palette.primary.main),
            "--mui-palette-secondary-main": palette.secondary.main,
            "--mui-palette-secondary-light": palette.secondary.light,
            "--mui-palette-secondary-dark": palette.secondary.dark,
            "--mui-palette-secondary-main-rgb": hexToRgb(
              palette.secondary.main,
            ),
            "--mui-palette-background-default": palette.background.default,
            "--mui-palette-background-paper": palette.background.paper,
            "--mui-palette-background-gradient-stop":
              palette.background.gradientStop,
            "--mui-palette-text-primary": palette.text.primary,
            "--mui-palette-text-secondary": palette.text.secondary,
            "--mui-palette-error-main": palette.error.main,
            "--mui-palette-warning-main": palette.warning.main,
            "--mui-palette-success-main": palette.success.main,
            "--mui-palette-divider": palette.divider,
          },
          body: {
            transition: "background-color 0.3s ease, color 0.3s ease",
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            textTransform: "none",
            borderRadius: 8,
          },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: {
            transition: "background-color 0.2s ease, transform 0.2s ease",
            "&:hover": {
              transform: "scale(1.1)",
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: "none",
          },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            fontSize: "0.85rem",
          },
        },
      },
    },
  });
}
