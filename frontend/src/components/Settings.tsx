import { useState } from "react";
import { Settings as SettingsIcon, Bell, Monitor, Shield, Lock, Unlock } from "lucide-react";
import { useHealthThresholds } from "../hooks/useHealthThresholds";
import { useGlassTheme } from "../hooks/useGlassTheme";
import { GLASS_PRESETS } from "../lib/settings";
import { ThresholdEditor } from "./ThresholdEditor";
import { SafetyRulesEditor } from "./SafetyRulesEditor";
import { PasswordModal } from "./PasswordModal";
import { NotificationSettings } from "./NotificationSettings";

interface SettingsProps {
  onError?: (error: string) => void;
}

export function Settings({ onError }: SettingsProps) {
  const { thresholds, loading, error, updateThresholds } = useHealthThresholds();
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [safetyRulesUnlocked, setSafetyRulesUnlocked] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);

  const handleSaveThresholds = async (newThresholds: {
    healthy: number;
    warning: number;
    critical: number;
  }) => {
    const success = await updateThresholds(newThresholds);
    if (success) {
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } else {
      onError?.("Failed to update thresholds");
    }
  };

  if (loading) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div className="text-center">
          <div
            className="animate-spin h-8 w-8 border-4 rounded-full mx-auto mb-4"
            style={{
              borderColor: "var(--color-sentinel-blue)",
              borderTopColor: "transparent",
            }}
          />
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <SettingsIcon className="h-8 w-8" style={{ color: "var(--color-sentinel-amber)" }} />
          <h1
            className="text-2xl font-semibold"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            System Settings
          </h1>
        </div>
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Configure global system settings and preferences
        </p>
      </div>

      {/* Success Message */}
      {saveSuccess && (
        <div
          className="mb-6 flex items-center gap-2 p-3 rounded-md"
          style={{
            background: "rgba(16, 185, 129, 0.15)",
            border: "1px solid rgba(16, 185, 129, 0.3)",
          }}
        >
          <div className="h-2 w-2 rounded-full" style={{ background: "var(--color-sentinel-green)" }} />
          <p className="text-sm" style={{ color: "var(--color-sentinel-green)" }}>
            Settings saved successfully
          </p>
        </div>
      )}

      {/* Settings Sections */}
      <div className="space-y-6 max-w-4xl">
        {/* Health Score Thresholds */}
        <div
          className="glass-panel overflow-hidden"
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{
                  background: "rgba(16, 185, 129, 0.15)",
                  color: "var(--color-sentinel-green)",
                }}
              >
                <Monitor className="h-5 w-5" />
              </div>
              <div>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Health Score Thresholds
                </h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Configure the health score boundaries for equipment classification
                </p>
              </div>
            </div>
          </div>

          <div className="p-4">
            {error ? (
              <div
                className="p-4 rounded-md text-center"
                style={{
                  background: "rgba(220, 38, 38, 0.15)",
                  border: "1px solid rgba(220, 38, 38, 0.3)",
                }}
              >
                <p style={{ color: "var(--color-sentinel-red)" }}>Failed to load thresholds</p>
              </div>
            ) : (
              <ThresholdEditor
                healthy={thresholds.healthy}
                warning={thresholds.warning}
                critical={thresholds.critical}
                onSave={handleSaveThresholds}
              />
            )}
          </div>
        </div>

        {/* Safety Rules */}
        <div
          className="glass-panel overflow-hidden"
          style={{
            border: safetyRulesUnlocked ? `1px solid var(--color-sentinel-amber)` : undefined,
          }}
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div
                  className="p-2 rounded"
                  style={{
                    background: "rgba(220, 38, 38, 0.15)",
                    color: "var(--color-sentinel-red)",
                  }}
                >
                  <Shield className="h-5 w-5" />
                </div>
                <div>
                  <h2
                    className="text-lg font-semibold"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    Safety Rules
                  </h2>
                  <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Configure safety interlocks and validation rules for device control
                  </p>
                </div>
              </div>

              {/* Lock/Unlock button */}
              <button
                onClick={() => {
                  if (safetyRulesUnlocked) {
                    setSafetyRulesUnlocked(false);
                  } else {
                    setShowPasswordModal(true);
                  }
                }}
                className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
                style={{
                  background: safetyRulesUnlocked
                    ? "rgba(245, 158, 11, 0.15)"
                    : "rgba(220, 38, 38, 0.15)",
                  color: safetyRulesUnlocked
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-red)",
                  border: `1px solid ${safetyRulesUnlocked ? "rgba(245, 158, 11, 0.3)" : "rgba(220, 38, 38, 0.3)"}`,
                }}
              >
                {safetyRulesUnlocked ? (
                  <>
                    <Unlock className="h-4 w-4" />
                    Lock Settings
                  </>
                ) : (
                  <>
                    <Lock className="h-4 w-4" />
                    Unlock to Edit
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Unlocked warning banner */}
          {safetyRulesUnlocked && (
            <div
              className="px-4 py-2 flex items-center gap-2"
              style={{
                background: "rgba(245, 158, 11, 0.15)",
                borderBottom: "1px solid rgba(245, 158, 11, 0.3)",
              }}
            >
              <Unlock className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
              <span className="text-sm" style={{ color: "var(--color-sentinel-amber)" }}>
                Safety Rules editing is unlocked. Click "Lock Settings" when finished.
              </span>
            </div>
          )}

          <div className="p-4">
            <SafetyRulesEditor
              onError={onError}
              onSuccess={() => {
                setSaveSuccess(true);
                setTimeout(() => setSaveSuccess(false), 3000);
              }}
              readOnly={!safetyRulesUnlocked}
            />
          </div>
        </div>

        {/* Notification Settings */}
        <div
          className="glass-panel overflow-hidden"
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{
                  background: "rgba(245, 158, 11, 0.15)",
                  color: "var(--color-sentinel-amber)",
                }}
              >
                <Bell className="h-5 w-5" />
              </div>
              <div>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Notification Settings
                </h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Configure alert commands and notification preferences for Clawd bot
                </p>
              </div>
            </div>
          </div>

          <div className="p-4">
            <NotificationSettings
              onError={onError}
              onSuccess={() => {
                setSaveSuccess(true);
                setTimeout(() => setSaveSuccess(false), 3000);
              }}
            />
          </div>
        </div>

        {/* Display Settings - Glass Theme Customization */}
        <div className="glass-panel overflow-hidden">
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{
                  background: "rgba(59, 130, 246, 0.15)",
                  color: "var(--color-sentinel-blue)",
                }}
              >
                <Monitor className="h-5 w-5" />
              </div>
              <div>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Display Settings
                </h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Customize Apple Glass theme appearance
                </p>
              </div>
            </div>
          </div>

          <div className="p-6">
            <GlassThemeControls />
          </div>
        </div>
      </div>

      {/* Password Modal for Safety Rules */}
      <PasswordModal
        isOpen={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        onSuccess={() => setSafetyRulesUnlocked(true)}
        title="Unlock Safety Rules"
        description="Safety rules control critical device limits. Enter the admin password to modify these settings."
      />
    </div>
  );
}

/**
 * Glass Theme Customization Controls
 *
 * Provides UI controls for customizing the Apple Glass theme:
 * - Master toggle to enable/disable custom theme
 * - Quick presets (default, subtle, heavy, minimal)
 * - Sliders for blur intensity, panel opacity, border strength
 * - Live preview panel showing glass effects
 * - Reset button to restore Phase 13 defaults
 */
function GlassThemeControls() {
  const { settings, updateSettings, resetToDefault, applyPreset } = useGlassTheme();

  return (
    <div className="space-y-6">
      {/* Master Toggle */}
      <div className="flex items-center justify-between">
        <div>
          <label
            className="font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Enable Custom Glass Theme
          </label>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Override default Apple Glass appearance
          </p>
        </div>
        <button
          onClick={() => updateSettings({ useCustomTheme: !settings.useCustomTheme })}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            settings.useCustomTheme ? "bg-blue-600" : "bg-gray-600"
          }`}
          aria-checked={settings.useCustomTheme}
          role="switch"
          type="button"
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
              settings.useCustomTheme ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>

      {settings.useCustomTheme && (
        <>
          {/* Preset Selector */}
          <div>
            <label
              className="block text-sm font-medium mb-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Quick Presets
            </label>
            <div className="grid grid-cols-4 gap-2">
              {Object.entries(GLASS_PRESETS).map(([name, preset]) => (
                <button
                  key={name}
                  onClick={() => applyPreset(name)}
                  className="px-3 py-2 text-sm rounded border capitalize transition-colors hover:bg-opacity-80"
                  style={{
                    borderColor: "var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                  type="button"
                >
                  {name}
                </button>
              ))}
            </div>
          </div>

          {/* Blur Intensity Slider */}
          <div>
            <div className="flex justify-between mb-2">
              <label
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Blur Intensity
              </label>
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {settings.blurIntensity}px
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="30"
              value={settings.blurIntensity}
              onChange={(e) => updateSettings({ blurIntensity: Number.parseInt(e.target.value, 10) })}
              className="w-full"
              aria-label="Blur intensity"
              aria-valuemin={0}
              aria-valuemax={30}
              aria-valuenow={settings.blurIntensity}
            />
            <div
              className="flex justify-between text-xs mt-1"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              <span>Subtle</span>
              <span>Sharp</span>
            </div>
          </div>

          {/* Panel Opacity Slider */}
          <div>
            <div className="flex justify-between mb-2">
              <label
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Panel Opacity
              </label>
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {settings.panelOpacity}%
              </span>
            </div>
            <input
              type="range"
              min="20"
              max="95"
              value={settings.panelOpacity}
              onChange={(e) => updateSettings({ panelOpacity: Number.parseInt(e.target.value, 10) })}
              className="w-full"
              aria-label="Panel opacity"
              aria-valuemin={20}
              aria-valuemax={95}
              aria-valuenow={settings.panelOpacity}
            />
            <div
              className="flex justify-between text-xs mt-1"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              <span>Transparent</span>
              <span>Solid</span>
            </div>
          </div>

          {/* Border Strength Slider */}
          <div>
            <div className="flex justify-between mb-2">
              <label
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Border Strength
              </label>
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {settings.borderStrength}%
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="40"
              value={settings.borderStrength}
              onChange={(e) => updateSettings({ borderStrength: Number.parseInt(e.target.value, 10) })}
              className="w-full"
              aria-label="Border strength"
              aria-valuemin={0}
              aria-valuemax={40}
              aria-valuenow={settings.borderStrength}
            />
            <div
              className="flex justify-between text-xs mt-1"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              <span>Invisible</span>
              <span>Prominent</span>
            </div>
          </div>

          {/* Live Preview Panel */}
          <div className="glass-card p-4 space-y-3">
            <p
              className="text-sm font-medium"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Live Preview
            </p>
            <div className="glass-panel p-4 space-y-2">
              <div className="glass-card p-3">
                <p className="text-sm">Nested card example</p>
              </div>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Adjust sliders above to see changes in real-time
              </p>
            </div>
          </div>
        </>
      )}

      {/* Reset Button */}
      <div
        className="pt-4 border-t"
        style={{ borderColor: "var(--color-sentinel-border)" }}
      >
        <button
          onClick={resetToDefault}
          className="px-4 py-2 text-sm rounded transition-colors hover:bg-opacity-80"
          style={{
            background: "var(--color-sentinel-bg-hover)",
            color: "var(--color-sentinel-text-primary)",
          }}
          type="button"
        >
          Reset to Default Theme
        </button>
      </div>
    </div>
  );
}

export default Settings;
