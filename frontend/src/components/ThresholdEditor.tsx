import { useState, useEffect } from "react";
import { Check, X, Info } from "lucide-react";

interface ThresholdEditorProps {
  healthy: number;
  warning: number;
  critical: number;
  onSave: (thresholds: { healthy: number; warning: number; critical: number }) => void;
  onCancel?: () => void;
  equipmentCount?: { healthy: number; warning: number; critical: number };
}

export function ThresholdEditor({
  healthy,
  warning,
  critical,
  onSave,
  onCancel,
  equipmentCount,
}: ThresholdEditorProps) {
  const [healthyValue, setHealthyValue] = useState(healthy);
  const [warningValue, setWarningValue] = useState(warning);
  const [criticalValue, setCriticalValue] = useState(critical);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Update local state when props change
  useEffect(() => {
    setHealthyValue(healthy);
    setWarningValue(warning);
    setCriticalValue(critical);
  }, [healthy, warning, critical]);

  const validate = (): boolean => {
    // Check ranges
    if (
      healthyValue < 0 ||
      healthyValue > 100 ||
      warningValue < 0 ||
      warningValue > 100 ||
      criticalValue < 0 ||
      criticalValue > 100
    ) {
      setValidationError("All thresholds must be between 0 and 100");
      return false;
    }

    // Check ordering
    if (healthyValue <= warningValue) {
      setValidationError("Healthy threshold must be greater than warning threshold");
      return false;
    }

    if (warningValue <= criticalValue) {
      setValidationError("Warning threshold must be greater than critical threshold");
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
      await onSave({ healthy: healthyValue, warning: warningValue, critical: criticalValue });
    } finally {
      setIsSaving(false);
    }
  };

  // Reserved for future use:
  // const getPreviewColor = (score: number): string => {
  //   if (score >= healthyValue) return "var(--color-sentinel-green)";
  //   if (score >= warningValue) return "var(--color-sentinel-amber)";
  //   return "var(--color-sentinel-red)";
  // };

  return (
    <div className="space-y-6">
      {/* Validation Error */}
      {validationError && (
        <div
          className="flex items-start gap-2 p-3 rounded-md"
          style={{
            background: "rgba(220, 38, 38, 0.15)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <X className="h-5 w-5 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-red)" }} />
          <div>
            <p className="font-medium text-sm" style={{ color: "var(--color-sentinel-red)" }}>
              Validation Error
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {validationError}
            </p>
          </div>
        </div>
      )}

      {/* Input Fields */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Critical Threshold */}
        <div>
          <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Critical Threshold
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={criticalValue}
            onChange={(e) => setCriticalValue(parseInt(e.target.value) || 0)}
            className="w-full px-3 py-2 rounded-md border focus:outline-none focus:ring-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Scores below {warningValue} are critical
          </p>
        </div>

        {/* Warning Threshold */}
        <div>
          <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Warning Threshold
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={warningValue}
            onChange={(e) => setWarningValue(parseInt(e.target.value) || 0)}
            className="w-full px-3 py-2 rounded-md border focus:outline-none focus:ring-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Scores {warningValue}-{healthyValue - 1} need attention
          </p>
        </div>

        {/* Healthy Threshold */}
        <div>
          <label className="block text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Healthy Threshold
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={healthyValue}
            onChange={(e) => setHealthyValue(parseInt(e.target.value) || 0)}
            className="w-full px-3 py-2 rounded-md border focus:outline-none focus:ring-2"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Scores {healthyValue}+ are healthy
          </p>
        </div>
      </div>

      {/* Visual Preview */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Info className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
          <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Threshold Preview
          </p>
        </div>

        {/* Color Bar */}
        <div className="h-8 rounded-md overflow-hidden flex">
          {/* Critical Range */}
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${warningValue}%`,
              background: "var(--color-sentinel-red)",
              color: "white",
            }}
          >
            Critical
          </div>
          {/* Warning Range */}
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${healthyValue - warningValue}%`,
              background: "var(--color-sentinel-amber)",
              color: "white",
            }}
          >
            Warning
          </div>
          {/* Healthy Range */}
          <div
            className="flex items-center justify-center text-xs font-medium"
            style={{
              width: `${100 - healthyValue}%`,
              background: "var(--color-sentinel-green)",
              color: "white",
            }}
          >
            Healthy
          </div>
        </div>

        {/* Score Markers */}
        <div className="relative h-6 mt-1">
          {/* Vertical divider lines */}
          <div
            className="absolute top-0 w-px"
            style={{ left: `${criticalValue}%`, height: "100%", background: "var(--color-sentinel-red)" }}
          />
          <div
            className="absolute top-0 w-px"
            style={{ left: `${warningValue}%`, height: "100%", background: "var(--color-sentinel-amber)" }}
          />
          <div
            className="absolute top-0 w-px"
            style={{ left: `${healthyValue}%`, height: "100%", background: "var(--color-sentinel-green)" }}
          />
          <div
            className="absolute top-0 w-px"
            style={{ left: "100%", height: "100%", background: "var(--color-sentinel-green)" }}
          />
          
          {/* Numbers positioned under divider lines */}
          <div className="absolute top-full mt-1 w-full">
            {/* 0 at left edge */}
            <span 
              className="absolute text-xs transform -translate-x-1/2"
              style={{ left: '0%', color: "var(--color-sentinel-text-disabled)" }}
            >
              0
            </span>
            {/* Critical value under red divider */}
            <span 
              className="absolute text-xs transform -translate-x-1/2"
              style={{ left: `${criticalValue}%`, color: "var(--color-sentinel-text-disabled)" }}
            >
              {criticalValue}
            </span>
            {/* Warning value under amber divider */}
            <span 
              className="absolute text-xs transform -translate-x-1/2"
              style={{ left: `${warningValue}%`, color: "var(--color-sentinel-text-disabled)" }}
            >
              {warningValue}
            </span>
            {/* Healthy value under green divider */}
            <span 
              className="absolute text-xs transform -translate-x-1/2"
              style={{ left: `${healthyValue}%`, color: "var(--color-sentinel-text-disabled)" }}
            >
              {healthyValue}
            </span>
            {/* 100 at right edge */}
            <span 
              className="absolute text-xs transform translate-x-1/2"
              style={{ right: '0%', color: "var(--color-sentinel-text-disabled)" }}
            >
              100
            </span>
          </div>
        </div>
      </div>

      {/* Equipment Count Preview */}
      {equipmentCount && (
        <div>
          <p className="text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Equipment Classification Preview
          </p>
          <div className="grid grid-cols-3 gap-3">
            <div
              className="p-3 rounded-md text-center"
              style={{
                background: "rgba(16, 185, 129, 0.15)",
                border: "1px solid rgba(16, 185, 129, 0.3)",
              }}
            >
              <p className="text-2xl font-semibold" style={{ color: "var(--color-sentinel-green)" }}>
                {equipmentCount.healthy}
              </p>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Healthy
              </p>
            </div>
            <div
              className="p-3 rounded-md text-center"
              style={{
                background: "rgba(245, 158, 11, 0.15)",
                border: "1px solid rgba(245, 158, 11, 0.3)",
              }}
            >
              <p className="text-2xl font-semibold" style={{ color: "var(--color-sentinel-amber)" }}>
                {equipmentCount.warning}
              </p>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Warning
              </p>
            </div>
            <div
              className="p-3 rounded-md text-center"
              style={{
                background: "rgba(220, 38, 38, 0.15)",
                border: "1px solid rgba(220, 38, 38, 0.3)",
              }}
            >
              <p className="text-2xl font-semibold" style={{ color: "var(--color-sentinel-red)" }}>
                {equipmentCount.critical}
              </p>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Critical
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center gap-3 pt-4" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 rounded-md transition-colors disabled:opacity-50"
          style={{
            background: isSaving ? "var(--color-sentinel-text-disabled)" : "var(--color-sentinel-blue)",
            color: "white",
          }}
        >
          {isSaving ? (
            <>Saving...</>
          ) : (
            <>
              <Check className="h-4 w-4" />
              Save Changes
            </>
          )}
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-md transition-colors"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

export default ThresholdEditor;
