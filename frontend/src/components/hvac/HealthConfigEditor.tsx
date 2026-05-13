/**
 * HealthConfigEditor - Engineer-configurable health calculation parameters
 *
 * Features:
 * - Edit health weights per equipment type
 * - Adjust thresholds for warnings/critical
 * - Configure fault weights
 * - Reset to defaults
 */

import { useState, useEffect } from "react";
import { Save, RotateCcw, AlertTriangle, CheckCircle, Info } from "lucide-react";
import { healthConfigApi, type EquipmentHealthConfig, type HealthWeights, type HealthThresholds } from "../../lib/hvacApi";

interface HealthConfigEditorProps {
  onConfigChange?: (equipmentType: string, config: EquipmentHealthConfig) => void;
}

export function HealthConfigEditor({ onConfigChange }: HealthConfigEditorProps) {
  const [configs, setConfigs] = useState<Record<string, EquipmentHealthConfig>>({});
  const [selectedType, setSelectedType] = useState<string>("chiller");
  const [editedConfig, setEditedConfig] = useState<Partial<EquipmentHealthConfig> | null>(null);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    loadConfigs();
  }, []);

  useEffect(() => {
    if (configs[selectedType]) {
      setEditedConfig({ ...configs[selectedType] });
    }
  }, [selectedType, configs]);

  async function loadConfigs() {
    try {
      const response = await healthConfigApi.list();
      setConfigs(response.configs);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load health configs");
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!editedConfig) return;

    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const result = await healthConfigApi.update(selectedType, {
        expected_life_years: editedConfig.expected_life_years,
        service_interval_days: editedConfig.service_interval_days,
        weights: editedConfig.weights,
        thresholds: editedConfig.thresholds,
        fault_weights: editedConfig.fault_weights,
      });

      setConfigs((prev) => ({
        ...prev,
        [selectedType]: result.config,
      }));
      setSuccessMessage(`Configuration saved for ${selectedType}`);
      onConfigChange?.(selectedType, result.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const result = await healthConfigApi.reset(selectedType);
      setConfigs((prev) => ({
        ...prev,
        [selectedType]: result.config,
      }));
      setEditedConfig({ ...result.config });
      setSuccessMessage(`Configuration reset to defaults for ${selectedType}`);
      onConfigChange?.(selectedType, result.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset configuration");
    } finally {
      setSaving(false);
    }
  }

  function updateWeight(key: keyof HealthWeights, value: number) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      weights: {
        ...editedConfig.weights!,
        [key]: value,
      },
    });
  }

  function updateThreshold(key: keyof HealthThresholds, value: number) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      thresholds: {
        ...editedConfig.thresholds!,
        [key]: value,
      },
    });
  }

  function updateFaultWeight(key: string, value: number) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      fault_weights: {
        ...editedConfig.fault_weights,
        [key]: value,
      },
    });
  }

  function validateWeights(): boolean {
    if (!editedConfig?.weights) return true;
    const sum = Object.values(editedConfig.weights).reduce((a, b) => a + b, 0);
    return Math.abs(sum - 1) < 0.01;
  }

  function validateFaultWeights(): boolean {
    if (!editedConfig?.fault_weights) return true;
    const sum = Object.values(editedConfig.fault_weights).reduce((a, b) => a + b, 0);
    return Math.abs(sum - 1) < 0.01;
  }

  if (loading) {
    return (
      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Health Calculation Configuration</h3>
        <div className="animate-pulse space-y-4 mt-4">
          <div className="h-32 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
          <div className="h-32 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }} />
        </div>
      </div>
    );
  }

  const equipmentTypes = Object.keys(configs);
  const typeLabels: Record<string, string> = {
    chiller: "Chillers",
    ahu: "AHUs",
    fcu: "FCUs",
    vav: "VAV Boxes",
    cooling_tower: "Cooling Towers",
    pump: "Pumps",
  };

  const weightsValid = validateWeights();
  const faultWeightsValid = validateFaultWeights();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-lg" style={{ color: "var(--color-sentinel-text-primary)" }}>Health Calculation Configuration</h3>
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Configure how health scores are calculated for each equipment type</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleReset}
            disabled={saving}
            className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border font-medium"
            style={{
              background: "transparent",
              color: "var(--color-sentinel-text-primary)",
              borderColor: "var(--color-sentinel-border)",
              opacity: saving ? 0.5 : 1,
              cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            <RotateCcw className="w-4 h-4" />
            Reset to Defaults
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !weightsValid || !faultWeightsValid}
            className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border font-medium"
            style={{
              background: "var(--color-sentinel-blue)",
              color: "white",
              borderColor: "var(--color-sentinel-blue)",
              opacity: saving || !weightsValid || !faultWeightsValid ? 0.5 : 1,
              cursor: saving || !weightsValid || !faultWeightsValid ? "not-allowed" : "pointer",
            }}
          >
            <Save className="w-4 h-4" />
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md p-4" style={{ background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)" }}>
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="text-red-300">{error}</span>
          </div>
        </div>
      )}

      {successMessage && (
        <div className="rounded-md p-4" style={{ background: "rgba(34, 197, 94, 0.1)", border: "1px solid rgba(34, 197, 94, 0.3)" }}>
          <div className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            <span className="text-green-300">{successMessage}</span>
          </div>
        </div>
      )}

      <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
        <span className="font-medium mb-3 block">Equipment Type</span>
        <div className="flex gap-2 flex-wrap">
          {equipmentTypes.map((type) => (
            <button
              key={type}
              onClick={() => setSelectedType(type)}
              className="px-2.5 py-1 text-xs rounded border font-medium"
              style={{
                background: selectedType === type ? "var(--color-sentinel-blue)" : "transparent",
                color: selectedType === type ? "white" : "var(--color-sentinel-text-primary)",
                borderColor: selectedType === type ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)",
                cursor: "pointer",
              }}
            >
              {typeLabels[type] || type}
            </button>
          ))}
        </div>
      </div>

      {editedConfig && (
        <div>
          <div className="flex border-b mb-4 overflow-x-auto" style={{ borderColor: "var(--color-sentinel-border)" }}>
            {["General", "Weights", "Thresholds", "Faults"].map((tab, idx) => (
              <button
                key={tab}
                onClick={() => setActiveTabIndex(idx)}
                className="px-4 py-2 text-sm font-medium whitespace-nowrap"
                style={{
                  color: activeTabIndex === idx ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-disabled)",
                  borderBottom: activeTabIndex === idx ? "2px solid var(--color-sentinel-blue)" : "2px solid transparent",
                  background: "none",
                  borderTop: "none",
                  borderLeft: "none",
                  borderRight: "none",
                  cursor: "pointer",
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeTabIndex === 0 && (
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Expected Life (Years)
                  </label>
                  <input
                    type="number"
                    value={editedConfig.expected_life_years || 20}
                    onChange={(e) =>
                      setEditedConfig({
                        ...editedConfig,
                        expected_life_years: parseInt(e.target.value) || 20,
                      })
                    }
                    min={1}
                    max={100}
                    className="w-full px-3 py-2 rounded-md"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                  <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    Typical lifespan for this equipment type
                  </span>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Service Interval (Days)
                  </label>
                  <input
                    type="number"
                    value={editedConfig.service_interval_days || 90}
                    onChange={(e) =>
                      setEditedConfig({
                        ...editedConfig,
                        service_interval_days: parseInt(e.target.value) || 90,
                      })
                    }
                    min={1}
                    max={365}
                    className="w-full px-3 py-2 rounded-md"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                  <span className="text-xs mt-1 block" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    Recommended service frequency
                  </span>
                </div>
              </div>
            </div>
          )}

          {activeTabIndex === 1 && (
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center justify-between mb-4">
                <span className="font-medium">Weight Distribution</span>
                <span
                  className="text-xs px-2 py-0.5 rounded font-medium"
                  style={{
                    background: weightsValid ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                    color: weightsValid ? "rgb(34, 197, 94)" : "rgb(239, 68, 68)",
                  }}
                >
                  Sum: {editedConfig.weights
                    ? Object.values(editedConfig.weights).reduce((a, b) => a + b, 0).toFixed(2)
                    : "0"}{" "}
                  {weightsValid ? "✓" : "(must equal 1.0)"}
                </span>
              </div>

              <div className="space-y-4">
                {editedConfig.weights &&
                  Object.entries(editedConfig.weights).map(([key, value]) => (
                    <div key={key}>
                      <div className="flex justify-between mb-1">
                        <label className="text-sm capitalize">
                          {key.replace(/_/g, " ")}
                        </label>
                        <span className="text-sm font-medium">{(value * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={value * 100}
                        onChange={(e) =>
                          updateWeight(key as keyof HealthWeights, parseInt(e.target.value) / 100)
                        }
                        className="w-full h-2 rounded-full appearance-none cursor-pointer"
                        style={{
                          background: `linear-gradient(to right, var(--color-sentinel-blue) 0%, var(--color-sentinel-blue) ${value * 100}%, var(--color-sentinel-border) ${value * 100}%, var(--color-sentinel-border) 100%)`,
                        }}
                      />
                    </div>
                  ))}
              </div>

              <div className="flex items-start gap-2 mt-4 p-3 rounded" style={{ background: "rgba(59, 130, 246, 0.1)", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
                <Info className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
                <span className="text-xs text-blue-300">
                  Weights determine how much each factor contributes to the overall health score.
                  They must sum to 100%.
                </span>
              </div>
            </div>
          )}

          {activeTabIndex === 2 && (
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <span className="font-medium mb-4 block">Warning & Critical Thresholds</span>

              <div className="grid grid-cols-2 gap-6">
                {editedConfig.thresholds &&
                  Object.entries(editedConfig.thresholds).map(([key, value]) => {
                    const isWarning = key.includes("warning");
                    const label = key
                      .replace(/_/g, " ")
                      .replace("warning", "(Warning)")
                      .replace("critical", "(Critical)");

                    return (
                      <div key={key}>
                        <label className="block text-sm font-medium mb-2 capitalize">
                          {label}
                        </label>
                        <input
                          type="number"
                          value={value}
                          onChange={(e) =>
                            updateThreshold(
                              key as keyof HealthThresholds,
                              parseInt(e.target.value) || 0
                            )
                          }
                          min={0}
                          className="w-full px-3 py-2 rounded-md"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            border: `1px solid ${isWarning ? "var(--color-sentinel-amber)" : "var(--color-sentinel-red)"}`,
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        />
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          {activeTabIndex === 3 && (
            <div className="rounded-md p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
              <div className="flex items-center justify-between mb-4">
                <span className="font-medium">Fault Type Weights</span>
                <span
                  className="text-xs px-2 py-0.5 rounded font-medium"
                  style={{
                    background: faultWeightsValid ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                    color: faultWeightsValid ? "rgb(34, 197, 94)" : "rgb(239, 68, 68)",
                  }}
                >
                  Sum:{" "}
                  {editedConfig.fault_weights
                    ? Object.values(editedConfig.fault_weights).reduce((a, b) => a + b, 0).toFixed(2)
                    : "0"}{" "}
                  {faultWeightsValid ? "✓" : "(must equal 1.0)"}
                </span>
              </div>

              <div className="space-y-4">
                {editedConfig.fault_weights &&
                  Object.entries(editedConfig.fault_weights).map(([key, value]) => (
                    <div key={key}>
                      <div className="flex justify-between mb-1">
                        <label className="text-sm capitalize">
                          {key.replace(/_/g, " ")}
                        </label>
                        <span className="text-sm font-medium">{(value * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={value * 100}
                        onChange={(e) =>
                          updateFaultWeight(key, parseInt(e.target.value) / 100)
                        }
                        className="w-full h-2 rounded-full appearance-none cursor-pointer"
                        style={{
                          background: `linear-gradient(to right, var(--color-sentinel-amber) 0%, var(--color-sentinel-amber) ${value * 100}%, var(--color-sentinel-border) ${value * 100}%, var(--color-sentinel-border) 100%)`,
                        }}
                      />
                    </div>
                  ))}
              </div>

              <div className="flex items-start gap-2 mt-4 p-3 rounded" style={{ background: "rgba(217, 119, 6, 0.1)", border: "1px solid rgba(217, 119, 6, 0.3)" }}>
                <Info className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <span className="text-xs text-amber-300">
                  Fault weights determine how different fault types impact the health score.
                  Higher weights mean more severe impact on equipment health.
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default HealthConfigEditor;
