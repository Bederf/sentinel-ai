/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

// ============================================================
// Theme System — Sentinel BMS
// Supports: sentinel (default), matrix, glass, ops, teal
// ============================================================

export type ThemeId = "sentinel" | "matrix" | "glass" | "ops" | "teal";

export interface ThemeDefinition {
  id: ThemeId;
  label: string;
  description: string;
  /** CSS class applied to <html> or root wrapper */
  className: string;
  /** Accent color shown in the switcher preview swatch */
  accentColor: string;
  /** Icon emoji for quick identification */
  icon: string;
}

export const THEMES: Record<ThemeId, ThemeDefinition> = {
  sentinel: {
    id: "sentinel",
    label: "Sentinel Dark",
    description: "Grafana-inspired dark panels with brand colors",
    className: "",
    accentColor: "#F59E0B",
    icon: "\u{1F6E1}",
  },
  matrix: {
    id: "matrix",
    label: "Matrix",
    description: "Cyberpunk terminal with neon green HUD",
    className: "matrix-theme",
    accentColor: "#00FF41",
    icon: "\u{1F7E2}",
  },
  glass: {
    id: "glass",
    label: "Glass",
    description: "Apple-style glassmorphism with blur effects",
    className: "glass-theme",
    accentColor: "#60A5FA",
    icon: "\u{1F48E}",
  },
  ops: {
    id: "ops",
    label: "Dark Ops",
    description: "Command center aesthetic \u2014 Bloomberg meets Figma",
    className: "ops-theme",
    accentColor: "#00d2ff",
    icon: "\u26A1",
  },
  teal: {
    id: "teal",
    label: "Teal",
    description: "SENTINEL brand palette \u2014 teal + amber on charcoal",
    className: "teal-theme",
    accentColor: "#00A89D",
    icon: "\u{1F30A}",
  },
};

export const THEME_IDS = Object.keys(THEMES) as ThemeId[];

const STORAGE_KEY = "sentinel_theme";

interface ThemeContextValue {
  theme: ThemeId;
  themeConfig: ThemeDefinition;
  setTheme: (id: ThemeId) => void;
  cycleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialTheme(): ThemeId {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && stored in THEMES) return stored as ThemeId;
  } catch {
    // localStorage unavailable
  }
  return "sentinel";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(getInitialTheme);

  const setTheme = useCallback((id: ThemeId) => {
    setThemeState(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // localStorage unavailable
    }
  }, []);

  const cycleTheme = useCallback(() => {
    setThemeState((current) => {
      const idx = THEME_IDS.indexOf(current);
      const next = THEME_IDS[(idx + 1) % THEME_IDS.length];
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // noop
      }
      return next;
    });
  }, []);

  // Apply theme class to <html> so CSS can scope globally
  useEffect(() => {
    const root = document.documentElement;
    // Remove all theme classes
    THEME_IDS.forEach((id) => {
      const cls = THEMES[id].className;
      if (cls) root.classList.remove(cls);
    });
    // Add current
    const cls = THEMES[theme].className;
    if (cls) root.classList.add(cls);

    // Also set a data attribute for CSS selectors
    root.dataset.theme = theme;
  }, [theme]);

  const value: ThemeContextValue = {
    theme,
    themeConfig: THEMES[theme],
    setTheme,
    cycleTheme,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}
