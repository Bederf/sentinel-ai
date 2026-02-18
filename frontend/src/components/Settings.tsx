import { useState } from "react";
import { Settings as SettingsIcon, Bell, Monitor, Shield, Lock, Unlock, Zap } from "lucide-react";
import { useHealthThresholds } from "../hooks/useHealthThresholds";
import { useGlassTheme } from "../hooks/useGlassTheme";
import { GLASS_PRESETS } from "../lib/settings";
import { ThresholdEditor } from "./ThresholdEditor";
import { SafetyRulesEditor } from "./SafetyRulesEditor";
import { PasswordModal } from "./PasswordModal";
import { NotificationSettings } from "./NotificationSettings";
import { ThemeSwitcher } from "./ThemeSwitcher";
import { useModules } from "../contexts/ModuleHooks";
import type { ModuleType } from "../lib/moduleRegistry";

interface SettingsProps {
  onError?: (error: string) => void;
}

interface FeatureToggleCard {
  id: string;
  label: string;
  moduleType: ModuleType;
  description: string;
  note?: string;
}

const BASE_PACK_LOCKED_MODULES: ModuleType[] = ["hvac", "energy"];

const FEATURE_TOGGLE_CARDS: FeatureToggleCard[] = [
  { id: "building-controls", label: "Building Controls", moduleType: "control", description: "Core control dashboard and automation orchestration." },
  { id: "ai-recommendations", label: "AI Recommendations", moduleType: "energy", description: "Core AI recommendation feed used across base dashboards.", note: "Base pack module (linked to Energy Centre)" },
  { id: "asset-workflow", label: "Asset Workflow", moduleType: "assets", description: "Lifecycle, maintenance workflows, and asset tracking." },
  { id: "simbiot", label: "SIMBIOT", moduleType: "simbiot", description: "Integration setup and onboarding tools, including Solar setup flow." },
  { id: "tech-chat", label: "Tech Chat", moduleType: "notifications", description: "Technician chat workflows and messaging-assisted diagnostics." },
  { id: "loadshedding", label: "Loadshedding", moduleType: "solar", description: "Loadshedding planning and response workflows.", note: "Linked to Solar & BESS module" },
  { id: "occupancy", label: "Occupancy", moduleType: "lighting", description: "Occupancy and lighting behavior controls." },
  { id: "security", label: "Security", moduleType: "security", description: "Access and security monitoring pages." },
  { id: "solar-bess", label: "Solar & BESS", moduleType: "solar", description: "Solar PV and battery storage monitoring." },
  { id: "water", label: "Water", moduleType: "water", description: "Water usage analytics and anomaly monitoring." },
  { id: "esg", label: "ESG", moduleType: "sustainability", description: "Sustainability and ESG dashboards." },
  { id: "contract", label: "Contract", moduleType: "contracts", description: "Contract management features and lifecycle." },
  { id: "profitability", label: "Profitability", moduleType: "contracts", description: "Profitability analytics views.", note: "Linked to Contract module" },
  { id: "budget-reports", label: "Budget Reports", moduleType: "contracts", description: "Budget and forecasting report views.", note: "Linked to Contract module" },
  { id: "fleet-ml", label: "Fleet ML", moduleType: "ml", description: "Cross-site ML insights and fleet analytics." },
  { id: "ml-metrics", label: "ML Metrics", moduleType: "ml", description: "MLOps and model monitoring metrics.", note: "Linked to ML module" },
  { id: "simulation", label: "Simulation", moduleType: "ml", description: "Simulation view for admin users.", note: "Linked to ML module" },
];

export function Settings({ onError }: SettingsProps) {
  const { thresholds, loading, error, updateThresholds } = useHealthThresholds();
  const { isModuleActive, activateModule, deactivateModule } = useModules();
  const currentUserEmail = (() => {
    try {
      const raw = localStorage.getItem("sentinel_user");
      if (!raw) return "";
      const parsed = JSON.parse(raw) as { email?: string };
      return parsed.email || "";
    } catch {
      return "";
    }
  })();
  const currentUserRole = (() => {
    try {
      const raw = localStorage.getItem("sentinel_user");
      if (!raw) return "auditor";
      const parsed = JSON.parse(raw) as { role?: string };
      return parsed.role || "auditor";
    } catch {
      return "auditor";
    }
  })();
  const demoUserEmails = ['grant@wardew.co.za', 'bederf@protonmail.com', 'bederf@gmail.com'];
  const isDemoUser = !!(currentUserEmail && demoUserEmails.includes(currentUserEmail.toLowerCase()));
  const canManageFeatureAccess = currentUserRole === "admin";
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [settingsPageUnlocked, setSettingsPageUnlocked] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [togglingCardId, setTogglingCardId] = useState<string | null>(null);

  const handleFeatureToggle = async (card: FeatureToggleCard) => {
    // Demo users need to unlock Settings page first
    if (isDemoUser && !settingsPageUnlocked) {
      onError?.(
        "Settings page is locked. Click 'Unlock to Edit' at the top to make changes."
      );
      return;
    }

    if (!canManageFeatureAccess && !isDemoUser) {
      onError?.("Only admins can change feature access.");
      return;
    }
    const currentlyActive = isModuleActive(card.moduleType);
    const locked = currentlyActive && BASE_PACK_LOCKED_MODULES.includes(card.moduleType);
    if (locked) return;

    setTogglingCardId(card.id);
    try {
      if (currentlyActive) {
        await deactivateModule(card.moduleType);
      } else {
        await activateModule(card.moduleType);
      }
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update feature toggle";
      onError?.(message);
    } finally {
      setTogglingCardId(null);
    }
  };

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
      {/* Header with Page-Level Unlock */}
      <div className="mb-6">
        <div className="flex items-center justify-between gap-3 mb-2">
          <div className="flex items-center gap-3">
            <SettingsIcon className="h-8 w-8" style={{ color: "var(--color-sentinel-amber)" }} />
            <h1
              className="text-2xl font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              System Settings
            </h1>
          </div>

          {/* Page-Level Lock/Unlock Button (Demo Users Only) */}
          {isDemoUser && (
            <button
              onClick={() => {
                if (settingsPageUnlocked) {
                  setSettingsPageUnlocked(false);
                } else {
                  setShowPasswordModal(true);
                }
              }}
              className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
              style={{
                background: settingsPageUnlocked
                  ? "rgba(245, 158, 11, 0.15)"
                  : "rgba(220, 38, 38, 0.15)",
                color: settingsPageUnlocked
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-red)",
                border: `1px solid ${settingsPageUnlocked ? "rgba(245, 158, 11, 0.3)" : "rgba(220, 38, 38, 0.3)"}`,
              }}
            >
              {settingsPageUnlocked ? (
                <>
                  <Lock className="h-4 w-4" />
                  Lock Settings
                </>
              ) : (
                <>
                  <Unlock className="h-4 w-4" />
                  Unlock to Edit
                </>
              )}
            </button>
          )}
        </div>
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Configure global system settings and preferences
        </p>
      </div>

      {/* Unlocked Warning Banner (Page Level) */}
      {isDemoUser && settingsPageUnlocked && (
        <div
          className="mb-6 flex items-center gap-2 p-3 rounded-md"
          style={{
            background: "rgba(245, 158, 11, 0.15)",
            border: "1px solid rgba(245, 158, 11, 0.3)",
          }}
        >
          <Unlock className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
          <span className="text-sm" style={{ color: "var(--color-sentinel-amber)" }}>
            Settings page is unlocked. Click "Lock Settings" when finished making changes.
          </span>
        </div>
      )}

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
        <div className="glass-panel overflow-hidden">
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
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
          </div>

          <div className="p-4">
            <SafetyRulesEditor
              onError={onError}
              onSuccess={() => {
                setSaveSuccess(true);
                setTimeout(() => setSaveSuccess(false), 3000);
              }}
              readOnly={!!(isDemoUser && !settingsPageUnlocked)}
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
                  Configure alert commands and notification preferences for SENTRY bot
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

        {/* Module Management */}
        <div
          className="glass-panel overflow-hidden"
          style={{
            background: "var(--glass-bg)",
            border: "1px solid var(--glass-border)",
          }}
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded-lg"
                style={{
                  background: "rgba(245, 158, 11, 0.15)",
                  color: "var(--color-sentinel-amber)",
                }}
              >
                <Zap className="h-5 w-5" />
              </div>
              <div>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Feature Access
                </h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Toggle these pages and capabilities for this site
                </p>
              </div>
            </div>
          </div>

          <div className="p-6">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {FEATURE_TOGGLE_CARDS.map((card) => {
                const active = isModuleActive(card.moduleType);
                const loadingCard = togglingCardId === card.id;
                const locked = active && BASE_PACK_LOCKED_MODULES.includes(card.moduleType);
                return (
                  <div
                    key={card.id}
                    className="rounded-lg p-4"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--glass-border)",
                      opacity: loadingCard ? 0.75 : 1,
                    }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {card.label}
                        </h3>
                        <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          {card.description}
                        </p>
                        {card.note && (
                          <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-blue)" }}>
                            {card.note}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => void handleFeatureToggle(card)}
                        disabled={loadingCard || locked || !canManageFeatureAccess}
                        className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
                        style={{
                          background: active ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
                          border: `1px solid ${active ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
                          cursor: loadingCard || locked || !canManageFeatureAccess ? "not-allowed" : "pointer",
                          opacity: loadingCard || locked || !canManageFeatureAccess ? 0.6 : 1,
                        }}
                        aria-label={`Toggle ${card.label}`}
                        type="button"
                      >
                        <span
                          className="inline-block h-4 w-4 rounded-full bg-white transition-transform"
                          style={{ transform: active ? "translateX(22px)" : "translateX(2px)" }}
                        />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <div
              className="mt-4 rounded-lg p-3"
              style={{
                background: "rgba(59, 130, 246, 0.08)",
                border: "1px solid rgba(59, 130, 246, 0.25)",
              }}
            >
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Solar Setup is managed in the SIMBIOT flow. Module management is handled on this Settings page.
              </p>
              {!canManageFeatureAccess && (
                <p className="text-xs mt-2" style={{ color: "var(--color-sentinel-amber)" }}>
                  You have read-only access. Contact an administrator to request module changes.
                </p>
              )}
            </div>
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

          <div className="p-6 space-y-6">
            {/* Theme Switcher */}
            <div className="space-y-3">
              <label
                className="block text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Select Theme
              </label>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Switch between Sentinel Dark, Matrix, Glass, and Dark Ops themes
              </p>
              <ThemeSwitcher />
            </div>

            {/* Separator */}
            <div
              style={{
                height: "1px",
                background: "var(--color-sentinel-border)",
              }}
            />

            {/* Glass Theme Customization */}
            <GlassThemeControls />
          </div>
        </div>
      </div>

      {/* Password Modal */}
      <PasswordModal
        isOpen={showPasswordModal}
        onClose={() => setShowPasswordModal(false)}
        onSuccess={() => {
          setSettingsPageUnlocked(true);
        }}
        title="Unlock Settings Page"
        description="This page requires a password to modify settings. Enter the admin password to make changes to safety rules, feature access, and other configurations."
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
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {Object.entries(GLASS_PRESETS).map(([name]) => (
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
              className="w-full h-3"
              style={{ cursor: "pointer" }}
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
              className="w-full h-3"
              style={{ cursor: "pointer" }}
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
              className="w-full h-3"
              style={{ cursor: "pointer" }}
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
