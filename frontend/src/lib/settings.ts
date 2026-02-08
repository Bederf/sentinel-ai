/**
 * Glass Theme Settings Types and Constants
 *
 * Provides type definitions and presets for Apple Glass theme customization.
 * Users can adjust blur intensity, panel opacity, and border strength.
 */

/**
 * Glass theme customization settings
 * - blurIntensity: Controls backdrop blur amount (0-30px, default 12)
 * - panelOpacity: Controls glass panel transparency (0-100%, default 65)
 * - borderStrength: Controls border visibility (0-100%, default 12)
 * - useCustomTheme: Master toggle for custom theme (default false)
 */
export interface GlassThemeSettings {
  blurIntensity: number;      // 0-30, default 12
  panelOpacity: number;       // 0-100, default 65
  borderStrength: number;     // 0-100, default 12
  useCustomTheme: boolean;    // Master toggle, default false
}

/**
 * Default glass theme values matching Phase 13 Apple Glass implementation
 */
export const DEFAULT_GLASS_THEME: GlassThemeSettings = {
  blurIntensity: 12,
  panelOpacity: 65,
  borderStrength: 12,
  useCustomTheme: false,
};

/**
 * Predefined glass theme presets
 * - default: Original Phase 13 values
 * - subtle: Reduced blur and opacity for lighter appearance
 * - heavy: Increased blur and opacity for stronger glass effect
 * - minimal: Minimal blur and opacity for subtle glass hint
 */
export const GLASS_PRESETS: Record<string, GlassThemeSettings> = {
  default: DEFAULT_GLASS_THEME,
  subtle: {
    blurIntensity: 6,
    panelOpacity: 45,
    borderStrength: 8,
    useCustomTheme: true,
  },
  heavy: {
    blurIntensity: 20,
    panelOpacity: 85,
    borderStrength: 22,
    useCustomTheme: true,
  },
  minimal: {
    blurIntensity: 3,
    panelOpacity: 30,
    borderStrength: 5,
    useCustomTheme: true,
  },
};
