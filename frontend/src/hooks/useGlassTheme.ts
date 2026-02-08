/**
 * Glass Theme Customization Hook
 *
 * Manages Apple Glass theme customization with localStorage persistence
 * and real-time CSS variable updates.
 */

import { useEffect, useState } from "react";
import type { GlassThemeSettings } from "@/lib/settings";
import { DEFAULT_GLASS_THEME, GLASS_PRESETS } from "@/lib/settings";

const STORAGE_KEY = "sentinel_glass_theme";

/**
 * Hook for managing glass theme settings
 *
 * Provides:
 * - settings: Current theme settings
 * - updateSettings: Update individual settings
 * - resetToDefault: Reset to Phase 13 defaults
 * - applyPreset: Apply a predefined preset theme
 *
 * Settings persist in localStorage and apply CSS variables to :root element
 */
export function useGlassTheme() {
  const [settings, setSettings] = useState<GlassThemeSettings>(() => {
    // Load from localStorage on mount
    if (typeof window === "undefined") return DEFAULT_GLASS_THEME;

    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_GLASS_THEME;

    try {
      return JSON.parse(stored);
    } catch {
      return DEFAULT_GLASS_THEME;
    }
  });

  // Apply theme whenever settings change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    applyGlassTheme(settings);
  }, [settings]);

  /**
   * Update specific theme settings
   * @param updates Partial settings to update
   */
  const updateSettings = (updates: Partial<GlassThemeSettings>) => {
    setSettings((prev) => ({ ...prev, ...updates }));
  };

  /**
   * Reset all settings to Phase 13 defaults
   */
  const resetToDefault = () => {
    setSettings(DEFAULT_GLASS_THEME);
  };

  /**
   * Apply a predefined preset theme
   * @param presetName Name of preset (default, subtle, heavy, minimal)
   */
  const applyPreset = (presetName: string) => {
    const preset = GLASS_PRESETS[presetName];
    if (preset) {
      setSettings(preset);
    }
  };

  return { settings, updateSettings, resetToDefault, applyPreset };
}

/**
 * Apply glass theme settings to CSS variables
 *
 * Converts user-friendly settings (blurIntensity, panelOpacity, borderStrength)
 * into CSS variable values for the glass theme system.
 *
 * Calculates derived values:
 * - blurSm: 50% of blurIntensity
 * - blurLg: 167% of blurIntensity
 * - bgLight: 69% of panelOpacity
 * - bgHeavy: 131% of panelOpacity (max 95%)
 * - borderStrong: 183% of borderStrength
 *
 * @param settings Glass theme settings to apply
 */
function applyGlassTheme(settings: GlassThemeSettings): void {
  if (typeof window === "undefined") return;

  const root = document.documentElement;

  // Calculate derived blur values
  const blurSm = Math.round(settings.blurIntensity * 0.5);
  const blurLg = Math.round(settings.blurIntensity * 1.67);

  // Calculate derived opacity values
  const bgLight = Math.round(settings.panelOpacity * 0.69);
  const bgHeavy = Math.round(Math.min(settings.panelOpacity * 1.31, 95));

  // Calculate derived border strength
  const borderStrong = Math.round(settings.borderStrength * 1.83);

  // Apply blur CSS variables
  root.style.setProperty("--glass-blur", `${settings.blurIntensity}px`);
  root.style.setProperty("--glass-blur-sm", `${blurSm}px`);
  root.style.setProperty("--glass-blur-lg", `${blurLg}px`);

  // Apply opacity CSS variables
  root.style.setProperty("--glass-bg", `rgba(33, 38, 45, ${settings.panelOpacity / 100})`);
  root.style.setProperty("--glass-bg-light", `rgba(33, 38, 45, ${bgLight / 100})`);
  root.style.setProperty("--glass-bg-heavy", `rgba(33, 38, 45, ${bgHeavy / 100})`);

  // Apply border CSS variables
  root.style.setProperty("--glass-border", `rgba(255, 255, 255, ${settings.borderStrength / 100})`);
  root.style.setProperty("--glass-border-strong", `rgba(255, 255, 255, ${borderStrong / 100})`);
}
