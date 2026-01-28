import { useState, useEffect } from "react";
import { Shield, AlertTriangle, Ban, Bell, Plus, Trash2, Edit2, Check, X, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "../lib/api";
import type { SafetyRule } from "../lib/api";

interface SafetyRulesEditorProps {
  onError?: (error: string) => void;
  onSuccess?: (message: string) => void;
  readOnly?: boolean; // If true, hide edit/create/delete controls
}

const RULE_TYPES = [
  { value: "temperature_range", label: "Temperature Range" },
  { value: "pressure_limit", label: "Pressure Limit" },
  { value: "brightness_limit", label: "Brightness Limit" },
  { value: "runtime_limit", label: "Runtime Limit" },
  { value: "interlock", label: "Interlock" },
  { value: "custom", label: "Custom" },
];

const SEVERITIES = [
  { value: "block", label: "Block", icon: Ban, color: "var(--color-sentinel-red)" },
  { value: "warning", label: "Warning", icon: AlertTriangle, color: "var(--color-sentinel-amber)" },
  { value: "alarm", label: "Alarm", icon: Bell, color: "var(--color-sentinel-blue)" },
];

const DEVICE_TYPES = [
  { value: "", label: "All Devices" },
  { value: "hvac", label: "HVAC" },
  { value: "lighting", label: "Lighting" },
  { value: "security", label: "Security" },
  { value: "fire_safety", label: "Fire Safety" },
];

export function SafetyRulesEditor({ onError, onSuccess, readOnly = false }: SafetyRulesEditorProps) {
  const [rules, setRules] = useState<SafetyRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedRule, setExpandedRule] = useState<string | null>(null);
  const [editingRule, setEditingRule] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<SafetyRule>>({});
  const [isCreating, setIsCreating] = useState(false);
  const [newRule, setNewRule] = useState<Partial<SafetyRule>>({
    name: "",
    rule_type: "temperature_range",
    severity: "warning",
    description: "",
    device_type: null,
    device_id: null,
    point_name: null,
    enabled: true,
    min_temp: 16,
    max_temp: 28,
    unit: "°C",
  });

  useEffect(() => {
    loadRules();
  }, []);

  const loadRules = async () => {
    try {
      setLoading(true);
      const response = await api.getSafetyRules();
      setRules(response.rules);
    } catch (err) {
      onError?.("Failed to load safety rules");
      console.error("Failed to load safety rules:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (ruleId: string, currentEnabled: boolean) => {
    try {
      await api.toggleSafetyRule(ruleId, !currentEnabled);
      setRules(rules.map(r => r.id === ruleId ? { ...r, enabled: !currentEnabled } : r));
      onSuccess?.(`Rule ${!currentEnabled ? "enabled" : "disabled"}`);
    } catch (err) {
      onError?.("Failed to toggle rule");
      console.error("Failed to toggle rule:", err);
    }
  };

  const handleDelete = async (ruleId: string) => {
    if (!confirm("Are you sure you want to delete this safety rule?")) return;

    try {
      await api.deleteSafetyRule(ruleId);
      setRules(rules.filter(r => r.id !== ruleId));
      onSuccess?.("Rule deleted successfully");
    } catch (err) {
      onError?.("Failed to delete rule");
      console.error("Failed to delete rule:", err);
    }
  };

  const handleEdit = (rule: SafetyRule) => {
    setEditingRule(rule.id);
    setEditForm({ ...rule });
  };

  const handleSaveEdit = async () => {
    if (!editingRule) return;

    try {
      const response = await api.updateSafetyRule(editingRule, editForm);
      setRules(rules.map(r => r.id === editingRule ? response.rule : r));
      setEditingRule(null);
      setEditForm({});
      onSuccess?.("Rule updated successfully");
    } catch (err) {
      onError?.("Failed to update rule");
      console.error("Failed to update rule:", err);
    }
  };

  const handleCancelEdit = () => {
    setEditingRule(null);
    setEditForm({});
  };

  const handleCreate = async () => {
    // Generate a unique ID based on name
    const ruleId = newRule.name?.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "") || `rule_${Date.now()}`;

    try {
      const ruleData = {
        ...newRule,
        id: ruleId,
      };

      const response = await api.createSafetyRule(ruleData);
      setRules([...rules, response.rule]);
      setIsCreating(false);
      setNewRule({
        name: "",
        rule_type: "temperature_range",
        severity: "warning",
        description: "",
        device_type: null,
        device_id: null,
        point_name: null,
        enabled: true,
        min_temp: 16,
        max_temp: 28,
        unit: "°C",
      });
      onSuccess?.("Rule created successfully");
    } catch (err) {
      onError?.("Failed to create rule");
      console.error("Failed to create rule:", err);
    }
  };

  const getSeverityIcon = (severity: string) => {
    const sev = SEVERITIES.find(s => s.value === severity);
    if (!sev) return null;
    const Icon = sev.icon;
    return <Icon className="h-4 w-4" style={{ color: sev.color }} />;
  };

  const getRuleTypeLabel = (type: string) => {
    return RULE_TYPES.find(t => t.value === type)?.label || type;
  };

  const renderRuleParameters = (rule: SafetyRule) => {
    switch (rule.rule_type) {
      case "temperature_range":
        return (
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Range: {rule.min_temp}°C - {rule.max_temp}°C
          </div>
        );
      case "pressure_limit":
        return (
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Range: {rule.min_pressure} - {rule.max_pressure} {rule.unit || "kPa"}
          </div>
        );
      case "brightness_limit":
        return (
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Range: {rule.min_brightness}% - {rule.max_brightness}%
          </div>
        );
      case "runtime_limit":
        return (
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Min runtime: {rule.min_runtime_minutes} min, Max starts/hr: {rule.max_starts_per_hour}
          </div>
        );
      case "interlock":
        return (
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Trigger: {rule.trigger_device_id || rule.trigger_device_type} → {rule.action}
          </div>
        );
      case "custom":
        return (
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {rule.validation_logic || `Range: ${rule.min_value} - ${rule.max_value}`}
          </div>
        );
      default:
        return null;
    }
  };

  const renderEditForm = (_rule: SafetyRule) => {
    return (
      <div className="p-4 space-y-4" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Name
            </label>
            <input
              type="text"
              value={editForm.name || ""}
              onChange={e => setEditForm({ ...editForm, name: e.target.value })}
              className="w-full px-3 py-2 rounded text-sm"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Severity
            </label>
            <select
              value={editForm.severity || "warning"}
              onChange={e => setEditForm({ ...editForm, severity: e.target.value as SafetyRule["severity"] })}
              className="w-full px-3 py-2 rounded text-sm"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {SEVERITIES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Description
          </label>
          <textarea
            value={editForm.description || ""}
            onChange={e => setEditForm({ ...editForm, description: e.target.value })}
            className="w-full px-3 py-2 rounded text-sm"
            rows={2}
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
        </div>

        {/* Rule-type specific fields */}
        {editForm.rule_type === "temperature_range" && (
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Min Temp (°C)
              </label>
              <input
                type="number"
                value={editForm.min_temp ?? 16}
                onChange={e => setEditForm({ ...editForm, min_temp: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Max Temp (°C)
              </label>
              <input
                type="number"
                value={editForm.max_temp ?? 28}
                onChange={e => setEditForm({ ...editForm, max_temp: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Point Name
              </label>
              <input
                type="text"
                value={editForm.point_name || ""}
                onChange={e => setEditForm({ ...editForm, point_name: e.target.value || null })}
                placeholder="e.g., cooling_setpoint"
                className="w-full px-3 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>
          </div>
        )}

        {editForm.rule_type === "brightness_limit" && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Min Brightness (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={editForm.min_brightness ?? 0}
                onChange={e => setEditForm({ ...editForm, min_brightness: parseInt(e.target.value) })}
                className="w-full px-3 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Max Brightness (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={editForm.max_brightness ?? 100}
                onChange={e => setEditForm({ ...editForm, max_brightness: parseInt(e.target.value) })}
                className="w-full px-3 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={handleCancelEdit}
            className="px-4 py-2 rounded text-sm flex items-center gap-2"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            <X className="h-4 w-4" />
            Cancel
          </button>
          <button
            onClick={handleSaveEdit}
            className="px-4 py-2 rounded text-sm flex items-center gap-2"
            style={{
              background: "var(--color-sentinel-green)",
              color: "white",
            }}
          >
            <Check className="h-4 w-4" />
            Save Changes
          </button>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="p-8 text-center">
        <div
          className="animate-spin h-8 w-8 border-4 rounded-full mx-auto mb-4"
          style={{
            borderColor: "var(--color-sentinel-blue)",
            borderTopColor: "transparent",
          }}
        />
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading safety rules...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Add button (hidden in read-only mode) */}
      <div className="flex items-center justify-between">
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {rules.length} rule{rules.length !== 1 ? "s" : ""} configured
        </p>
        {!readOnly && (
          <button
            onClick={() => setIsCreating(true)}
            className="px-3 py-1.5 rounded text-sm flex items-center gap-2"
            style={{
              background: "rgba(59, 130, 246, 0.15)",
              color: "var(--color-sentinel-blue)",
              border: "1px solid rgba(59, 130, 246, 0.3)",
            }}
          >
            <Plus className="h-4 w-4" />
            Add Rule
          </button>
        )}
      </div>

      {/* Create new rule form */}
      {isCreating && (
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-blue)",
          }}
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
            <h3 className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Create New Safety Rule
            </h3>
          </div>
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Name *
                </label>
                <input
                  type="text"
                  value={newRule.name || ""}
                  onChange={e => setNewRule({ ...newRule, name: e.target.value })}
                  placeholder="e.g., Zone Temperature Limit"
                  className="w-full px-3 py-2 rounded text-sm"
                  style={{
                    background: "var(--color-sentinel-bg-canvas)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Rule Type
                </label>
                <select
                  value={newRule.rule_type || "temperature_range"}
                  onChange={e => setNewRule({ ...newRule, rule_type: e.target.value as SafetyRule["rule_type"] })}
                  className="w-full px-3 py-2 rounded text-sm"
                  style={{
                    background: "var(--color-sentinel-bg-canvas)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  {RULE_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Severity
                </label>
                <select
                  value={newRule.severity || "warning"}
                  onChange={e => setNewRule({ ...newRule, severity: e.target.value as SafetyRule["severity"] })}
                  className="w-full px-3 py-2 rounded text-sm"
                  style={{
                    background: "var(--color-sentinel-bg-canvas)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  {SEVERITIES.map(s => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Device Type
                </label>
                <select
                  value={newRule.device_type || ""}
                  onChange={e => setNewRule({ ...newRule, device_type: e.target.value || null })}
                  className="w-full px-3 py-2 rounded text-sm"
                  style={{
                    background: "var(--color-sentinel-bg-canvas)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                >
                  {DEVICE_TYPES.map(d => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Description
              </label>
              <textarea
                value={newRule.description || ""}
                onChange={e => setNewRule({ ...newRule, description: e.target.value })}
                placeholder="Describe what this rule does and why it's important"
                className="w-full px-3 py-2 rounded text-sm"
                rows={2}
                style={{
                  background: "var(--color-sentinel-bg-canvas)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>

            {/* Temperature range fields */}
            {newRule.rule_type === "temperature_range" && (
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Min Temp (°C)
                  </label>
                  <input
                    type="number"
                    value={newRule.min_temp ?? 16}
                    onChange={e => setNewRule({ ...newRule, min_temp: parseFloat(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Max Temp (°C)
                  </label>
                  <input
                    type="number"
                    value={newRule.max_temp ?? 28}
                    onChange={e => setNewRule({ ...newRule, max_temp: parseFloat(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Point Name
                  </label>
                  <input
                    type="text"
                    value={newRule.point_name || ""}
                    onChange={e => setNewRule({ ...newRule, point_name: e.target.value || null })}
                    placeholder="e.g., cooling_setpoint"
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Brightness limit fields */}
            {newRule.rule_type === "brightness_limit" && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Min Brightness (%)
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={newRule.min_brightness ?? 0}
                    onChange={e => setNewRule({ ...newRule, min_brightness: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Max Brightness (%)
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={newRule.max_brightness ?? 100}
                    onChange={e => setNewRule({ ...newRule, max_brightness: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Pressure limit fields */}
            {newRule.rule_type === "pressure_limit" && (
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Min Pressure
                  </label>
                  <input
                    type="number"
                    value={newRule.min_pressure ?? 0}
                    onChange={e => setNewRule({ ...newRule, min_pressure: parseFloat(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Max Pressure
                  </label>
                  <input
                    type="number"
                    value={newRule.max_pressure ?? 100}
                    onChange={e => setNewRule({ ...newRule, max_pressure: parseFloat(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Unit
                  </label>
                  <input
                    type="text"
                    value={newRule.unit || "kPa"}
                    onChange={e => setNewRule({ ...newRule, unit: e.target.value })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Runtime limit fields */}
            {newRule.rule_type === "runtime_limit" && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Min Runtime (minutes)
                  </label>
                  <input
                    type="number"
                    min={0}
                    value={newRule.min_runtime_minutes ?? 5}
                    onChange={e => setNewRule({ ...newRule, min_runtime_minutes: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Max Starts per Hour
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={newRule.max_starts_per_hour ?? 4}
                    onChange={e => setNewRule({ ...newRule, max_starts_per_hour: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-canvas)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsCreating(false)}
                className="px-4 py-2 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-canvas)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!newRule.name}
                className="px-4 py-2 rounded text-sm"
                style={{
                  background: newRule.name ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-disabled)",
                  color: newRule.name ? "white" : "var(--color-sentinel-text-disabled)",
                  cursor: newRule.name ? "pointer" : "not-allowed",
                }}
              >
                Create Rule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rules list */}
      <div className="space-y-2">
        {rules.map(rule => (
          <div
            key={rule.id}
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: `1px solid ${rule.enabled ? "var(--color-sentinel-border)" : "var(--color-sentinel-border-disabled)"}`,
              opacity: rule.enabled ? 1 : 0.7,
            }}
          >
            {/* Rule header */}
            <div
              className="p-3 flex items-center justify-between cursor-pointer"
              onClick={() => !readOnly && setExpandedRule(expandedRule === rule.id ? null : rule.id)}
            >
              <div className="flex items-center gap-3">
                {getSeverityIcon(rule.severity)}
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {rule.name}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded"
                      style={{
                        background: "var(--color-sentinel-bg-canvas)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      {getRuleTypeLabel(rule.rule_type)}
                    </span>
                  </div>
                  {renderRuleParameters(rule)}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Toggle switch (hidden in read-only) */}
                {!readOnly && (
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      handleToggle(rule.id, rule.enabled);
                    }}
                    className="relative w-10 h-5 rounded-full transition-colors"
                    style={{
                      background: rule.enabled ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-disabled)",
                    }}
                  >
                    <span
                      className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform"
                      style={{
                        left: rule.enabled ? "calc(100% - 18px)" : "2px",
                      }}
                    />
                  </button>
                )}

                {/* Expand/collapse icon (only in editable mode, or always show if expanded) */}
                {!readOnly || expandedRule === rule.id ? (
                  expandedRule === rule.id ? (
                    <ChevronUp className="h-5 w-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  ) : (
                    <ChevronDown className="h-5 w-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  )
                ) : null}
              </div>
            </div>

            {/* Expanded content */}
            {expandedRule === rule.id && (
              <>
                {editingRule === rule.id ? (
                  renderEditForm(rule)
                ) : (
                  <div className="px-3 pb-3 pt-0">
                    <div
                      className="p-3 rounded text-sm"
                      style={{
                        background: "var(--color-sentinel-bg-canvas)",
                        color: "var(--color-sentinel-text-secondary)",
                      }}
                    >
                      <p className="mb-2">{rule.description}</p>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span style={{ color: "var(--color-sentinel-text-disabled)" }}>ID:</span>{" "}
                          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{rule.id}</span>
                        </div>
                        <div>
                          <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Device Type:</span>{" "}
                          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{rule.device_type || "All"}</span>
                        </div>
                        {rule.device_id && (
                          <div>
                            <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Device ID:</span>{" "}
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{rule.device_id}</span>
                          </div>
                        )}
                        {rule.point_name && (
                          <div>
                            <span style={{ color: "var(--color-sentinel-text-disabled)" }}>Point:</span>{" "}
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{rule.point_name}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {!readOnly && (
                      <div className="flex justify-end gap-2 mt-3">
                        <button
                          onClick={() => handleEdit(rule)}
                          className="px-3 py-1.5 rounded text-sm flex items-center gap-1"
                          style={{
                            background: "rgba(59, 130, 246, 0.15)",
                            color: "var(--color-sentinel-blue)",
                          }}
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(rule.id)}
                          className="px-3 py-1.5 rounded text-sm flex items-center gap-1"
                          style={{
                            background: "rgba(220, 38, 38, 0.15)",
                            color: "var(--color-sentinel-red)",
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        ))}

        {rules.length === 0 && !isCreating && (
          <div
            className="p-8 text-center rounded-md"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <Shield className="h-12 w-12 mx-auto mb-3" style={{ color: "var(--color-sentinel-text-disabled)" }} />
            <p className="font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
              No Safety Rules Configured
            </p>
            <p className="text-sm mb-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {readOnly ? "Safety rules must be configured by an administrator" : "Create safety rules to protect your equipment and ensure safe operations"}
            </p>
            {!readOnly && (
              <button
                onClick={() => setIsCreating(true)}
                className="px-4 py-2 rounded text-sm inline-flex items-center gap-2"
                style={{
                  background: "var(--color-sentinel-blue)",
                  color: "white",
                }}
              >
                <Plus className="h-4 w-4" />
                Add Your First Rule
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default SafetyRulesEditor;
