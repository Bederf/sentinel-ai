import { useCallback, useEffect, useState } from "react";
import { Check, Info, X } from "lucide-react";

interface HealthValues {
  healthy: number;
  warning: number;
  critical: number;
}

interface RiskValues {
  medium: number;
  high: number;
  critical: number;
}

interface SiteThresholdEditorProps {
  health: HealthValues;
  risk: RiskValues;
  onSave: (thresholds: { health: HealthValues; risk: RiskValues }) => void;
  onCancel?: () => void;
}

function parseThresholdValue(rawValue: string): number {
  return Number.parseInt(rawValue, 10) || 0;
}

function validateHealth(values: HealthValues): string | null {
  if (!(0 <= values.critical && values.critical < values.warning && values.warning < values.healthy && values.healthy <= 100)) {
    return "Must satisfy: 0 ≤ critical < warning < healthy ≤ 100";
  }
  return null;
}

function validateRisk(values: RiskValues): string | null {
  if (!(0 <= values.medium && values.medium < values.high && values.high < values.critical && values.critical <= 100)) {
    return "Must satisfy: 0 ≤ medium < high < critical ≤ 100";
  }
  return null;
}

function ThresholdSlider({
  label,
  value,
  description,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  description: string;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-4">
      <span className="text-xs font-medium uppercase tracking-wider min-w-[5rem]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {label}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer"
        style={{
          background: `linear-gradient(to right, var(--color-sentinel-blue) ${value}%, var(--color-sentinel-border) ${value}%)`,
          accentColor: "var(--color-sentinel-blue)",
        }}
      />
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(parseThresholdValue(e.target.value))}
        className="w-16 px-2 py-1 text-xs text-right rounded border"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          borderColor: "var(--color-sentinel-border)",
          color: "var(--color-sentinel-text-primary)",
        }}
      />
      <span className="text-[10px] text-slate-500 max-w-[10rem] leading-tight hidden md:block">{description}</span>
    </div>
  );
}

export function SiteThresholdEditor({ health, risk, onSave, onCancel }: SiteThresholdEditorProps) {
  const [healthValues, setHealthValues] = useState(health);
  const [riskValues, setRiskValues] = useState(risk);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    setHealthValues(health);
    setRiskValues(risk);
  }, [health, risk]);

  useEffect(() => {
    setHealthError(validateHealth(healthValues));
  }, [healthValues]);

  useEffect(() => {
    setRiskError(validateRisk(riskValues));
  }, [riskValues]);

  const canSave = !healthError && !riskError;

  const handleSave = useCallback(async () => {
    if (!canSave) return;
    setIsSaving(true);
    try {
      await onSave({ health: healthValues, risk: riskValues });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } finally {
      setIsSaving(false);
    }
  }, [canSave, healthValues, riskValues, onSave]);

  return (
    <div className="space-y-6">
      {/* Health thresholds */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <div className="h-2 w-2 rounded-full bg-emerald-400/60" />
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Health Score Boundaries
          </span>
        </div>
        <div className="space-y-3">
          <ThresholdSlider
            label="Healthy ≥"
            value={healthValues.healthy}
            description="Score at or above this value is healthy"
            min={healthValues.warning + 1}
            max={100}
            onChange={(v) => setHealthValues((p) => ({ ...p, healthy: v }))}
          />
          <ThresholdSlider
            label="Warning ≥"
            value={healthValues.warning}
            description="Score between warning and healthy is caution"
            min={healthValues.critical + 1}
            max={healthValues.healthy - 1}
            onChange={(v) => setHealthValues((p) => ({ ...p, warning: v }))}
          />
          <ThresholdSlider
            label="Critical &lt;"
            value={healthValues.critical}
            description="Score below this value is critical"
            min={0}
            max={healthValues.warning - 1}
            onChange={(v) => setHealthValues((p) => ({ ...p, critical: v }))}
          />
        </div>
        {healthError && (
          <div className="mt-2 flex items-center gap-1.5 text-xs" style={{ color: "var(--color-sentinel-red)" }}>
            <Info className="h-3 w-3" />
            {healthError}
          </div>
        )}
      </div>

      {/* Risk thresholds */}
      <div className="border-t pt-4" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-2 mb-3">
          <div className="h-2 w-2 rounded-full bg-orange-400/60" />
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Risk Score Boundaries
          </span>
        </div>
        <div className="space-y-3">
          <ThresholdSlider
            label="Medium ≥"
            value={riskValues.medium}
            description="Score at or above this value is medium risk"
            min={0}
            max={riskValues.high - 1}
            onChange={(v) => setRiskValues((p) => ({ ...p, medium: v }))}
          />
          <ThresholdSlider
            label="High ≥"
            value={riskValues.high}
            description="Score at or above this value is high risk"
            min={riskValues.medium + 1}
            max={riskValues.critical - 1}
            onChange={(v) => setRiskValues((p) => ({ ...p, high: v }))}
          />
          <ThresholdSlider
            label="Critical ≥"
            value={riskValues.critical}
            description="Score at or above this value is critical risk"
            min={riskValues.high + 1}
            max={100}
            onChange={(v) => setRiskValues((p) => ({ ...p, critical: v }))}
          />
        </div>
        {riskError && (
          <div className="mt-2 flex items-center gap-1.5 text-xs" style={{ color: "var(--color-sentinel-red)" }}>
            <Info className="h-3 w-3" />
            {riskError}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={!canSave || isSaving}
          className="flex items-center gap-2 px-4 py-2 rounded text-xs font-medium uppercase tracking-wider transition-all disabled:opacity-40"
          style={{
            background: saveSuccess ? "rgba(16, 185, 129, 0.15)" : "var(--color-sentinel-blue)",
            color: saveSuccess ? "var(--color-sentinel-green)" : "white",
          }}
        >
          {saveSuccess ? (
            <><Check className="h-3.5 w-3.5" /> Saved</>
          ) : (
            <>{isSaving ? "Saving..." : "Save Thresholds"}</>
          )}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="flex items-center gap-2 px-4 py-2 rounded text-xs font-medium uppercase tracking-wider transition-all"
            style={{
              background: "rgba(255,255,255,0.05)",
              color: "var(--color-sentinel-text-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <X className="h-3.5 w-3.5" /> Cancel
          </button>
        )}
      </div>
    </div>
  );
}
