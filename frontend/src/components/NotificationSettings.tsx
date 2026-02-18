/**
 * NotificationSettings Component
 *
 * Manages alert command configuration for SENTRY Telegram bot:
 * - Toggle which commands appear on alert messages (reset, info, note, wo)
 * - Configure alert cooldown period
 * - Configure equipment types blocked from remote reset
 */

import { useState, useEffect, useCallback } from "react";
import { Save, RotateCcw, Info, StickyNote, Wrench, X } from "lucide-react";
import { authorizedFetch } from '@/lib/api';

interface AlertCommandConfig {
  enabled: boolean;
  label: string;
}

interface NotificationSettingsData {
  alertCommands: Record<string, AlertCommandConfig>;
  alertCooldownMinutes: number;
  resetBlockedTypes: string[];
}

const COMMAND_META: Record<string, { icon: React.ReactNode; description: string }> = {
  reset: {
    icon: <RotateCcw className="h-4 w-4" />,
    description: "Remote fault reset - restores equipment health to normal",
  },
  info: {
    icon: <Info className="h-4 w-4" />,
    description: "Show full equipment details, health, alerts, and predictions",
  },
  note: {
    icon: <StickyNote className="h-4 w-4" />,
    description: "Add a note to equipment record without creating a work order",
  },
  wo: {
    icon: <Wrench className="h-4 w-4" />,
    description: "Create work order with sub-options: minor, major, or inspection",
  },
};

const COMMAND_ORDER = ["reset", "info", "note", "wo"];

const COMMON_EQUIPMENT_TYPES = [
  "FIRE", "GEN", "UPS", "ATS", "CHILLER", "AHU", "FCU", "VAV", "DALI", "ACC", "CCTV",
];

interface NotificationSettingsProps {
  onSuccess?: () => void;
  onError?: (msg: string) => void;
}

export function NotificationSettings({ onSuccess, onError }: NotificationSettingsProps) {
  const [settings, setSettings] = useState<NotificationSettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [newBlockedType, setNewBlockedType] = useState("");

  const load = useCallback(async () => {
    try {
      const token = localStorage.getItem("sentinel_token");
      if (!token) {
        setLoading(false);
        return;
      }
      const response = await authorizedFetch("/api/settings/notifications");
      if (!response.ok) throw new Error("Failed to load");
      const data = await response.json();
      setSettings(data);
    } catch {
      onError?.("Failed to load notification settings");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    load();
  }, [load]);

  const handleToggleCommand = (key: string, enabled: boolean) => {
    if (!settings) return;
    setSettings({
      ...settings,
      alertCommands: {
        ...settings.alertCommands,
        [key]: { ...settings.alertCommands[key], enabled },
      },
    });
    setDirty(true);
  };

  const handleLabelChange = (key: string, label: string) => {
    if (!settings) return;
    setSettings({
      ...settings,
      alertCommands: {
        ...settings.alertCommands,
        [key]: { ...settings.alertCommands[key], label },
      },
    });
    setDirty(true);
  };

  const handleCooldownChange = (value: number) => {
    if (!settings) return;
    setSettings({ ...settings, alertCooldownMinutes: value });
    setDirty(true);
  };

  const handleAddBlockedType = () => {
    if (!settings || !newBlockedType.trim()) return;
    const type = newBlockedType.trim().toUpperCase();
    if (settings.resetBlockedTypes.includes(type)) return;
    setSettings({
      ...settings,
      resetBlockedTypes: [...settings.resetBlockedTypes, type],
    });
    setNewBlockedType("");
    setDirty(true);
  };

  const handleRemoveBlockedType = (type: string) => {
    if (!settings) return;
    setSettings({
      ...settings,
      resetBlockedTypes: settings.resetBlockedTypes.filter((t) => t !== type),
    });
    setDirty(true);
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const response = await authorizedFetch("/api/settings/notifications", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(settings),
      });
      if (!response.ok) throw new Error("Failed to save");
      setDirty(false);
      onSuccess?.();
    } catch {
      onError?.("Failed to save notification settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div
          className="animate-spin h-6 w-6 border-2 rounded-full"
          style={{
            borderColor: "var(--color-sentinel-amber)",
            borderTopColor: "transparent",
          }}
        />
      </div>
    );
  }

  if (!settings) {
    return (
      <p className="text-sm py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        Could not load notification settings.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Alert Command Toggles */}
      <div className="space-y-3">
        <h3
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Alert Message Commands
        </h3>
        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Choose which commands appear on Telegram alert messages
        </p>

        {COMMAND_ORDER.map((key) => {
          const meta = COMMAND_META[key];
          const cfg = settings.alertCommands?.[key];
          if (!meta || !cfg) return null;

          return (
            <div
              key={key}
              className="flex items-center justify-between p-3 rounded-lg"
              style={{
                background: cfg.enabled
                  ? "rgba(59, 130, 246, 0.08)"
                  : "var(--color-sentinel-bg-secondary)",
                border: `1px solid ${cfg.enabled ? "rgba(59, 130, 246, 0.25)" : "var(--color-sentinel-border)"}`,
              }}
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div
                  className="p-2 rounded flex-shrink-0"
                  style={{
                    background: cfg.enabled
                      ? "rgba(59, 130, 246, 0.2)"
                      : "var(--color-sentinel-bg-panel)",
                    color: cfg.enabled
                      ? "var(--color-sentinel-blue)"
                      : "var(--color-sentinel-text-secondary)",
                  }}
                >
                  {meta.icon}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--color-sentinel-bg-panel)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      /{key === "wo" ? "WO" : key}_
                    </span>
                    <input
                      type="text"
                      value={cfg.label}
                      onChange={(e) => handleLabelChange(key, e.target.value)}
                      className="text-sm font-medium bg-transparent border-0 outline-none"
                      style={{ color: "var(--color-sentinel-text-primary)", maxWidth: "180px" }}
                    />
                  </div>
                  <p
                    className="text-xs mt-0.5 truncate"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {meta.description}
                  </p>
                </div>
              </div>

              {/* Toggle switch */}
              <button
                onClick={() => handleToggleCommand(key, !cfg.enabled)}
                className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ml-3"
                style={{
                  background: cfg.enabled
                    ? "var(--color-sentinel-blue)"
                    : "var(--color-sentinel-bg-secondary)",
                  border: `1px solid ${cfg.enabled ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)"}`,
                }}
              >
                <span
                  className="inline-block h-4 w-4 rounded-full transition-transform bg-white"
                  style={{
                    transform: cfg.enabled ? "translateX(22px)" : "translateX(3px)",
                  }}
                />
              </button>
            </div>
          );
        })}
      </div>

      {/* Alert Cooldown */}
      <div className="space-y-3">
        <h3
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Alert Cooldown
        </h3>
        <div
          className="p-3 rounded-lg"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex items-center justify-between">
            <div>
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Cooldown period
              </span>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Minimum time between alerts for the same equipment
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                max={60}
                value={settings.alertCooldownMinutes}
                onChange={(e) => handleCooldownChange(parseInt(e.target.value) || 5)}
                className="w-16 rounded px-2 py-1 text-sm text-right border-0 outline-none"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                min
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Reset Blocked Types */}
      <div className="space-y-3">
        <h3
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Reset Blocked Equipment Types
        </h3>
        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Equipment types that cannot be remotely reset (safety-critical)
        </p>

        <div
          className="p-3 rounded-lg"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Current blocked types as tags */}
          <div className="flex flex-wrap gap-2 mb-3">
            {settings.resetBlockedTypes.map((type) => (
              <span
                key={type}
                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium"
                style={{
                  background: "rgba(220, 38, 38, 0.15)",
                  color: "var(--color-sentinel-red)",
                  border: "1px solid rgba(220, 38, 38, 0.3)",
                }}
              >
                {type}
                <button
                  onClick={() => handleRemoveBlockedType(type)}
                  className="hover:opacity-70"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            {settings.resetBlockedTypes.length === 0 && (
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                No types blocked - all equipment can be remotely reset
              </span>
            )}
          </div>

          {/* Add new blocked type */}
          <div className="flex items-center gap-2">
            <select
              value={newBlockedType}
              onChange={(e) => setNewBlockedType(e.target.value)}
              className="text-xs rounded px-2 py-1.5 border-0 outline-none flex-1"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <option value="">Add equipment type...</option>
              {COMMON_EQUIPMENT_TYPES.filter(
                (t) => !settings.resetBlockedTypes.includes(t)
              ).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <button
              onClick={handleAddBlockedType}
              disabled={!newBlockedType}
              className="px-3 py-1.5 rounded text-xs font-medium transition-colors"
              style={{
                background: newBlockedType
                  ? "rgba(220, 38, 38, 0.15)"
                  : "var(--color-sentinel-bg-panel)",
                color: newBlockedType
                  ? "var(--color-sentinel-red)"
                  : "var(--color-sentinel-text-disabled)",
                cursor: newBlockedType ? "pointer" : "default",
              }}
            >
              Block
            </button>
          </div>
        </div>
      </div>

      {/* Save button */}
      <button
        onClick={handleSave}
        disabled={!dirty || saving}
        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        style={{
          background: dirty ? "var(--color-sentinel-blue)" : "var(--color-sentinel-bg-secondary)",
          color: dirty ? "white" : "var(--color-sentinel-text-disabled)",
          opacity: saving ? 0.6 : 1,
          cursor: dirty && !saving ? "pointer" : "default",
        }}
      >
        {saving ? (
          <div
            className="h-4 w-4 border-2 rounded-full animate-spin"
            style={{ borderColor: "white", borderTopColor: "transparent" }}
          />
        ) : (
          <Save className="h-4 w-4" />
        )}
        {saving ? "Saving..." : "Save Settings"}
      </button>
    </div>
  );
}

export default NotificationSettings;
