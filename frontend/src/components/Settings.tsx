import { useState } from "react";
import { Settings as SettingsIcon, Bell, Monitor, Shield } from "lucide-react";
import { useHealthThresholds } from "../hooks/useHealthThresholds";
import { ThresholdEditor } from "./ThresholdEditor";
import { SafetyRulesEditor } from "./SafetyRulesEditor";

interface SettingsProps {
  onError?: (error: string) => void;
}

export function Settings({ onError }: SettingsProps) {
  const { thresholds, loading, error, updateThresholds } = useHealthThresholds();
  const [saveSuccess, setSaveSuccess] = useState(false);

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
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
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
              readOnly={true}
            />
          </div>
        </div>

        {/* Notification Settings - Coming Soon */}
        <div
          className="rounded-md overflow-hidden opacity-60"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
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
                  Configure alert notifications and delivery preferences
                </p>
              </div>
            </div>
          </div>

          <div className="p-8 text-center">
            <Bell className="h-12 w-12 mx-auto mb-3" style={{ color: "var(--color-sentinel-text-disabled)" }} />
            <p
              className="text-sm font-medium mb-1"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Coming Soon
            </p>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Notification settings will be available in a future update
            </p>
          </div>
        </div>

        {/* Display Settings - Coming Soon */}
        <div
          className="rounded-md overflow-hidden opacity-60"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
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
                  Customize data visualization and chart preferences
                </p>
              </div>
            </div>
          </div>

          <div className="p-8 text-center">
            <Monitor className="h-12 w-12 mx-auto mb-3" style={{ color: "var(--color-sentinel-text-disabled)" }} />
            <p
              className="text-sm font-medium mb-1"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Coming Soon
            </p>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Display settings will be available in a future update
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Settings;
