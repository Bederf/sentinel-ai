import { useEffect, useState } from "react";
import { Info, X } from "lucide-react";

interface RiskThresholdEditorProps {
  medium: number;
  high: number;
  critical: number;
  onSave: (thresholds: { medium: number; high: number; critical: number }) => void;
}

export function RiskThresholdEditor({
  medium,
  high,
  critical,
  onSave,
}: RiskThresholdEditorProps) {
  const [mediumValue, setMediumValue] = useState(medium);
  const [highValue, setHighValue] = useState(high);
  const [criticalValue, setCriticalValue] = useState(critical);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setMediumValue(medium);
    setHighValue(high);
    setCriticalValue(critical);
  }, [medium, high, critical]);

  const validate = (): boolean => {
    if (
      mediumValue < 0 ||
      mediumValue > 100 ||
      highValue < 0 ||
      highValue > 100 ||
      criticalValue < 0 ||
      criticalValue > 100
    ) {
      setValidationError("All thresholds must be between 0 and 100");
      return false;
    }

    if (highValue <= mediumValue) {
      setValidationError("High threshold must be greater than medium threshold");
      return false;
    }

    if (criticalValue <= highValue) {
      setValidationError("Critical threshold must be greater than high threshold");
      return false;
    }

    setValidationError(null);
    return true;
  };

  const handleSave = async () => {
    if (!validate()) {
      return;
    }

    setIsSaving(true);
    try {
      await onSave({ medium: mediumValue, high: highValue, critical: criticalValue });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {validationError && (
        <div
          className="flex items-start gap-2 rounded-md p-3"
          style={{
            background: "rgba(220, 38, 38, 0.15)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <X className="mt-0.5 h-5 w-5 flex-shrink-0" style={{ color: "var(--color-sentinel-red)" }} />
          <div>
            <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-red)" }}>
              Validation Error
            </p>
            <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {validationError}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <label className="mb-2 block text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Medium Threshold
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={mediumValue}
            onChange={(e) => setMediumValue(parseInt(e.target.value) || 0)}
            className="w-full rounded-md border px-3 py-2 focus:outline-none focus:ring-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Scores below {mediumValue} stay low
          </p>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            High Threshold
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={highValue}
            onChange={(e) => setHighValue(parseInt(e.target.value) || 0)}
            className="w-full rounded-md border px-3 py-2 focus:outline-none focus:ring-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Scores {mediumValue}-{highValue - 1} render as medium
          </p>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Critical Threshold
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={criticalValue}
            onChange={(e) => setCriticalValue(parseInt(e.target.value) || 0)}
            className="w-full rounded-md border px-3 py-2 focus:outline-none focus:ring-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Scores {criticalValue}+ render as critical
          </p>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <Info className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
          <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Threshold Preview
          </p>
        </div>

        <div className="flex h-8 overflow-hidden rounded-md">
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${mediumValue}%`,
              background: "#0ea5e9",
              color: "white",
            }}
          >
            Low
          </div>
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${highValue - mediumValue}%`,
              background: "#facc15",
              color: "#111827",
            }}
          >
            Medium
          </div>
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${criticalValue - highValue}%`,
              background: "#f97316",
              color: "white",
            }}
          >
            High
          </div>
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${100 - criticalValue}%`,
              background: "#ef4444",
              color: "white",
            }}
          >
            Critical
          </div>
        </div>

        <div className="mt-4 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="rounded-md px-4 py-2 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-blue)",
              color: "white",
            }}
          >
            {isSaving ? "Saving..." : "Save Thresholds"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default RiskThresholdEditor;
