import { useState, useCallback } from "react";
import { Settings as SettingsIcon, Bell, Monitor, Shield, Lock, Unlock, Zap, Gauge, Play, Pause } from "lucide-react";
import { useHealthThresholds } from "../hooks/useHealthThresholds";
import { useGlassTheme } from "../hooks/useGlassTheme";
import { GLASS_PRESETS } from "../lib/settings";
import { ThresholdEditor } from "./ThresholdEditor";
import { SafetyRulesEditor } from "./SafetyRulesEditor";
import { PasswordModal } from "./PasswordModal";
import { NotificationSettings } from "./NotificationSettings";
import { NotificationChannelsSettings } from "./NotificationChannelsSettings";
import { ThemeSwitcher } from "./ThemeSwitcher";
import { useModules } from "../contexts/ModuleHooks";
import { useSimulation } from "../contexts/SimulationContext";
import type { ModuleType } from "../lib/moduleRegistry";
import { MANDATORY_MODULES } from "../lib/mandatoryModules";
import { changeSimulationSpeed, pauseSimulation, resumeSimulation } from "../lib/simulationApi";

interface SettingsProps {
  onError?: (error: string) => void;
}

interface FeatureToggleCard {
  id: string;
  label: string;
  moduleType: ModuleType;
  description: string;
  note?: string;
  /** If true, this is a control toggle inside a building system card */
  isControlToggle?: boolean;
}

const BASE_PACK_LOCKED_MODULES: ModuleType[] = MANDATORY_MODULES;

/** Platform base modules — status indicators only, no toggles */
const PLATFORM_STATUS_CARDS: FeatureToggleCard[] = [
  { id: "kpi", label: "KPI Dashboard", moduleType: "kpi", description: "Portfolio and site KPI scorecards.", note: "Always on" },
  { id: "ml", label: "ML Intelligence", moduleType: "ml", description: "Anomaly detection and predictive maintenance.", note: "Always on" },
  { id: "notifications", label: "Notifications", moduleType: "notifications", description: "Alert routing and acknowledgement.", note: "Always on" },
  { id: "integrations", label: "System Health", moduleType: "integrations", description: "Integration health and data quality.", note: "Always on" },
  { id: "simbiot", label: "SIMBIOT", moduleType: "simbiot", description: "BMS connection wizard and data discovery.", note: "Always on" },
  { id: "logging", label: "Logging", moduleType: "logging", description: "Audit trail and event logs.", note: "Always on" },
  { id: "assets", label: "Assets", moduleType: "assets", description: "Asset registry and lifecycle.", note: "Always on" },
];

/** Building system cards — base always on, with optional control toggle inside */
interface BuildingSystemCard {
  id: string;
  label: string;
  baseModule: ModuleType;
  controlModule?: ModuleType;
  description: string;
}

const BUILDING_SYSTEM_CARDS: BuildingSystemCard[] = [
  { id: "hvac-system", label: "HVAC", baseModule: "hvac", controlModule: "hvac_control", description: "Heating, ventilation, and air conditioning." },
  { id: "energy-system", label: "Energy", baseModule: "energy", controlModule: "energy_control", description: "Power metering, generators, UPS." },
  { id: "lighting-system", label: "Lighting", baseModule: "lighting", controlModule: "lighting_control", description: "DALI lighting and occupancy." },
  { id: "solar-system", label: "Solar & BESS", baseModule: "solar", controlModule: "solar_control", description: "Solar PV and battery storage." },
  { id: "water-system", label: "Water", baseModule: "water", controlModule: "water_control", description: "Water monitoring and leak detection." },
  { id: "security-system", label: "Security", baseModule: "security", controlModule: "security_control", description: "Access control and CCTV." },
  { id: "fire-system", label: "Fire", baseModule: "fire", description: "Fire alarm monitoring (always read-only)." },
  { id: "twin-system", label: "Digital Twin", baseModule: "digital_twin", controlModule: "digital_twin_control", description: "3D/2D building visualization." },
];

/** Standalone add-on toggles */
const ADDON_TOGGLE_CARDS: FeatureToggleCard[] = [
  { id: "maintenance-addon", label: "Maintenance", moduleType: "maintenance", description: "Work orders, scheduling, technician dispatch." },
  { id: "financial-addon", label: "Financial", moduleType: "financial", description: "Contracts, profitability, budget, SLA." },
  { id: "compliance-addon", label: "Compliance", moduleType: "compliance", description: "Carbon Tax, Green Star, SANS, ESG." },
  { id: "simulation-addon", label: "Simulation", moduleType: "simulation", description: "What-if scenarios and ROI modelling." },
  { id: "fleet-ml-addon", label: "Fleet ML", moduleType: "fleet_ml", description: "Cross-portfolio analytics and benchmarking." },
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
  const demoUserEmails = ['grant@grantdemo.co.za', 'bederf@protonmail.com', 'bederf@gmail.com'];
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
        <NotificationSettingsPanel
          onError={onError}
          onSuccess={() => {
            setSaveSuccess(true);
            setTimeout(() => setSaveSuccess(false), 3000);
          }}
        />

        {/* Section 1: Platform Base (status indicators, no toggles) */}
        <div className="glass-panel overflow-hidden">
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
                <Zap className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Platform</h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Core platform modules (always active)</p>
              </div>
            </div>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {PLATFORM_STATUS_CARDS.map((card) => (
                <div key={card.id} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{card.label}</h3>
                      <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
                    </div>
                    <div className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>Active</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Section 2: Building Systems (base always on + control toggles inside) */}
        <div className="glass-panel overflow-hidden">
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
                <Gauge className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Building Systems</h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Monitoring always on. Toggle control features per discipline.</p>
              </div>
            </div>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {BUILDING_SYSTEM_CARDS.map((card) => {
                const controlActive = card.controlModule ? isModuleActive(card.controlModule) : false;
                const loadingCard = togglingCardId === card.id;
                const canToggle = canManageFeatureAccess || (isDemoUser && settingsPageUnlocked);
                return (
                  <div key={card.id} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: loadingCard ? 0.75 : 1 }}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{card.label}</h3>
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>Monitoring</span>
                        </div>
                        <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
                        {card.controlModule && (
                          <div className="mt-2 flex items-center gap-2">
                            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Control:</span>
                            <button
                              onClick={() => {
                                if (!canToggle) return;
                                const controlCard: FeatureToggleCard = { id: card.id, label: `${card.label} Control`, moduleType: card.controlModule!, description: "" };
                                void handleFeatureToggle(controlCard);
                              }}
                              disabled={loadingCard || !canToggle}
                              className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
                              style={{
                                background: controlActive ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
                                border: `1px solid ${controlActive ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
                                cursor: !canToggle ? "not-allowed" : "pointer",
                                opacity: !canToggle ? 0.6 : 1,
                              }}
                              aria-label={`Toggle ${card.label} control`}
                              type="button"
                            >
                              <span className="inline-block h-3 w-3 rounded-full bg-white transition-transform" style={{ transform: controlActive ? "translateX(17px)" : "translateX(2px)" }} />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Section 3: Add-ons (on/off toggles) */}
        <div className="glass-panel overflow-hidden" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ background: "rgba(168, 85, 247, 0.15)", color: "rgb(168, 85, 247)" }}>
                <Zap className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Add-ons</h2>
                <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Standalone features you can enable or disable</p>
              </div>
            </div>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {ADDON_TOGGLE_CARDS.map((card) => {
                const active = isModuleActive(card.moduleType);
                const loadingCard = togglingCardId === card.id;
                const canToggle = canManageFeatureAccess || (isDemoUser && settingsPageUnlocked);
                return (
                  <div key={card.id} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: loadingCard ? 0.75 : 1 }}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{card.label}</h3>
                        <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
                      </div>
                      <button
                        onClick={() => void handleFeatureToggle(card)}
                        disabled={loadingCard || !canToggle}
                        className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
                        style={{
                          background: active ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
                          border: `1px solid ${active ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
                          cursor: !canToggle ? "not-allowed" : "pointer",
                          opacity: !canToggle ? 0.6 : 1,
                        }}
                        aria-label={`Toggle ${card.label}`}
                        type="button"
                      >
                        <span className="inline-block h-4 w-4 rounded-full bg-white transition-transform" style={{ transform: active ? "translateX(22px)" : "translateX(2px)" }} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            {!canManageFeatureAccess && !(isDemoUser && settingsPageUnlocked) && (
              <div className="mt-4 rounded-lg p-3" style={{ background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.25)" }}>
                <p className="text-xs" style={{ color: "var(--color-sentinel-amber)" }}>
                  {isDemoUser ? "Unlock settings at the top of the page to toggle modules." : "You have read-only access. Contact an administrator to request module changes."}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Display Settings - Glass Theme Customization */}
        <div className="glass-panel overflow-visible">
          <div className="p-4 border-b rounded-t-lg" style={{ borderColor: "var(--color-sentinel-border)" }}>
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

        {/* Simulation Controls */}
        <SimulationControlsPanel
          readOnly={!!(isDemoUser && !settingsPageUnlocked)}
          onError={onError}
        />
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

// ========== Simulation Controls Panel ==========

const SPEED_PRESETS = [1, 5, 10, 50, 100] as const;

function SimulationControlsPanel({
  readOnly,
  onError,
}: {
  readOnly: boolean;
  onError?: (msg: string) => void;
}) {
  const sim = useSimulation();
  const [changingSpeed, setChangingSpeed] = useState(false);

  const handleSpeedChange = useCallback(
    async (speed: number) => {
      if (readOnly || changingSpeed) return;
      setChangingSpeed(true);
      try {
        await changeSimulationSpeed(speed);
        await sim.refresh();
      } catch (err) {
        onError?.(err instanceof Error ? err.message : "Failed to change speed");
      } finally {
        setChangingSpeed(false);
      }
    },
    [readOnly, changingSpeed, sim, onError]
  );

  const handlePauseResume = useCallback(async () => {
    if (readOnly) return;
    try {
      if (sim.paused) {
        await resumeSimulation();
      } else {
        await pauseSimulation();
      }
      await sim.refresh();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to pause/resume");
    }
  }, [readOnly, sim, onError]);

  // Convert linear slider (0-100) to log scale (0.1 - 1000)
  const speedToSlider = (speed: number) =>
    Math.round((Math.log10(Math.max(0.1, speed)) + 1) * 25);
  const sliderToSpeed = (val: number) =>
    Math.round(10 ** (val / 25 - 1) * 10) / 10;

  return (
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
            <Gauge className="h-5 w-5" />
          </div>
          <div>
            <h2
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Simulation Controls
            </h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Adjust simulation speed and view progress
            </p>
          </div>
        </div>
      </div>

      <div className="p-6">
        {!sim.running ? (
          <div
            className="rounded-lg p-4 text-center"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--glass-border)",
            }}
          >
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              No simulation running
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Current Speed + Day Progress */}
            <div className="flex flex-col sm:flex-row gap-4">
              <div
                className="flex-1 rounded-lg p-3"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--glass-border)",
                }}
              >
                <p className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Current Speed
                </p>
                <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {sim.speedMultiplier}x
                  <span
                    className="text-sm font-normal ml-2"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {sim.secondsPerHour.toFixed(1)}s per simulated hour
                  </span>
                </p>
              </div>
              <div
                className="flex-1 rounded-lg p-3"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--glass-border)",
                }}
              >
                <p className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Progress
                </p>
                <p className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Day {sim.daysSimulated} of 365
                  <span
                    className="text-sm font-normal ml-2"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {sim.progressPct}%
                  </span>
                </p>
                {/* Progress bar */}
                <div
                  className="mt-2 h-1.5 rounded-full overflow-hidden"
                  style={{ background: "var(--color-sentinel-bg-hover)" }}
                >
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${sim.progressPct}%`,
                      background: "var(--color-sentinel-blue)",
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Pause/Resume */}
            <div>
              <button
                onClick={() => void handlePauseResume()}
                disabled={readOnly}
                className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
                style={{
                  background: sim.paused
                    ? "rgba(16, 185, 129, 0.15)"
                    : "rgba(245, 158, 11, 0.15)",
                  color: sim.paused
                    ? "var(--color-sentinel-green)"
                    : "var(--color-sentinel-amber)",
                  border: `1px solid ${sim.paused ? "rgba(16, 185, 129, 0.3)" : "rgba(245, 158, 11, 0.3)"}`,
                  cursor: readOnly ? "not-allowed" : "pointer",
                  opacity: readOnly ? 0.6 : 1,
                }}
                type="button"
              >
                {sim.paused ? (
                  <>
                    <Play className="h-4 w-4" />
                    Resume Simulation
                  </>
                ) : (
                  <>
                    <Pause className="h-4 w-4" />
                    Pause Simulation
                  </>
                )}
              </button>
            </div>

            {/* Speed Presets */}
            <div>
              <label
                className="block text-sm font-medium mb-2"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Speed Presets
              </label>
              <div className="flex flex-wrap gap-2">
                {SPEED_PRESETS.map((speed) => {
                  const isActive = sim.speedMultiplier === speed;
                  return (
                    <button
                      key={speed}
                      onClick={() => void handleSpeedChange(speed)}
                      disabled={readOnly || changingSpeed}
                      className="px-4 py-2 text-sm rounded font-medium transition-colors"
                      style={{
                        background: isActive
                          ? "rgba(59, 130, 246, 0.25)"
                          : "var(--color-sentinel-bg-secondary)",
                        color: isActive
                          ? "var(--color-sentinel-blue)"
                          : "var(--color-sentinel-text-primary)",
                        border: `1px solid ${isActive ? "rgba(59, 130, 246, 0.4)" : "var(--glass-border)"}`,
                        cursor: readOnly || changingSpeed ? "not-allowed" : "pointer",
                        opacity: readOnly ? 0.6 : 1,
                      }}
                      type="button"
                    >
                      {speed}x
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Fine-Grained Slider (log scale) */}
            <div>
              <div className="flex justify-between mb-2">
                <label
                  className="text-sm font-medium"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Fine Control
                </label>
                <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {sim.speedMultiplier}x
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={speedToSlider(sim.speedMultiplier)}
                onChange={(e) => {
                  const speed = sliderToSpeed(Number.parseInt(e.target.value, 10));
                  void handleSpeedChange(speed);
                }}
                disabled={readOnly || changingSpeed}
                className="w-full h-3"
                style={{ cursor: readOnly ? "not-allowed" : "pointer" }}
                aria-label="Simulation speed"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={speedToSlider(sim.speedMultiplier)}
              />
              <div
                className="flex justify-between text-xs mt-1"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                <span>0.1x</span>
                <span>1x</span>
                <span>10x</span>
                <span>100x</span>
                <span>1000x</span>
              </div>
            </div>
          </div>
        )}
      </div>
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

// ========== Notification Settings Panel Component ==========

/**
 * Notification Settings Panel - Unified UI for notification configuration
 * Combines SENTRY bot settings with Phase 102 multi-channel notifications
 */
function NotificationSettingsPanel({
  onError,
  onSuccess,
}: {
  onError?: (msg: string) => void;
  onSuccess?: () => void;
}) {
  const [notifTab, setNotifTab] = useState<"sentry" | "channels">("channels");
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

  // Pass email — backend resolves to technician UUID via email lookup
  const technicianId = currentUserEmail || "technician";

  return (
    <div className="glass-panel overflow-hidden">
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
              Configure multi-channel notifications and SENTRY bot preferences
            </p>
          </div>
        </div>
      </div>

      <div className="p-4">
        {/* Tabs */}
        <div className="flex gap-2 border-b mb-6" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <button
            onClick={() => setNotifTab("channels")}
            className="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
            style={{
              borderColor:
                notifTab === "channels"
                  ? "var(--color-sentinel-blue)"
                  : "transparent",
              color:
                notifTab === "channels"
                  ? "var(--color-sentinel-blue)"
                  : "var(--color-sentinel-text-secondary)",
            }}
          >
            Multi-Channel (Phase 102)
          </button>
          <button
            onClick={() => setNotifTab("sentry")}
            className="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
            style={{
              borderColor:
                notifTab === "sentry"
                  ? "var(--color-sentinel-blue)"
                  : "transparent",
              color:
                notifTab === "sentry"
                  ? "var(--color-sentinel-blue)"
                  : "var(--color-sentinel-text-secondary)",
            }}
          >
            SENTRY Bot Alert Commands
          </button>
        </div>

        {/* Channels Tab */}
        {notifTab === "channels" && (
          <NotificationChannelsSettings
            technician_id={technicianId}
            onError={onError}
            onSuccess={onSuccess}
          />
        )}

        {/* SENTRY Bot Tab */}
        {notifTab === "sentry" && (
          <NotificationSettings
            onError={onError}
            onSuccess={onSuccess}
          />
        )}
      </div>
    </div>
  );
}

export default Settings;
