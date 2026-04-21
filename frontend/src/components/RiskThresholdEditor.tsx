import { useEffect, useState } from "react";
import { Info, X } from "lucide-react";

interface RiskThresholdEditorProps {
  medium: number;
  high: number;
  critical: number;
  onSave: (thresholds: { medium: number; high: number; critical: number }) => void;
}

interface RiskThresholdValues {
  medium: number;
  high: number;
  critical: number;
}

interface ThresholdInputCardProps {
  label: string;
  value: number;
  description: string;
  onChange: (value: number) => void;
}

function parseThresholdValue(rawValue: string): number {
  return Number.parseInt(rawValue, 10) || 0;
}

function validateRiskThresholds(values: RiskThresholdValues): string | null {
  if (
    values.medium < 0 ||
    values.medium > 100 ||
    values.high < 0 ||
    values.high > 100 ||
    values.critical < 0 ||
    values.critical > 100
  ) {
    return "All thresholds must be between 0 and 100";
  }

  if (values.high <= values.medium) {
    return "High threshold must be greater than medium threshold";
  }

  if (values.critical <= values.high) {
    return "Critical threshold must be greater than high threshold";
  }

  return null;
}

function ThresholdValidationError({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }

  return (
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
          {message}
        </p>
      </div>
    </div>
  );
}

function ThresholdInputCard({ label, value, description, onChange }: ThresholdInputCardProps) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
        {label}
      </label>
      <input
        type="number"
        min="0"
        max="100"
        value={value}
        onChange={(event) => onChange(parseThresholdValue(event.target.value))}
        className="w-full rounded-md border px-3 py-2 focus:outline-none focus:ring-2"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
          color: "var(--color-sentinel-text-primary)",
        }}
      />
      <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {description}
      </p>
    </div>
  );
}

function ThresholdPreview({
  values,
  isSaving,
  onSave,
}: {
  values: RiskThresholdValues;
  isSaving: boolean;
  onSave: () => void;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Info className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
        <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Threshold Preview
        </p>
      </div>
      <ThresholdPreviewBars values={values} />
      <ThresholdSaveAction isSaving={isSaving} onSave={onSave} />
    </div>
  );
}

function ThresholdPreviewBars({ values }: { values: RiskThresholdValues }) {
  return (
    <div className="flex h-8 overflow-hidden rounded-md">
      <ThresholdPreviewBand label="Low" width={values.medium} background="var(--color-sentinel-blue)" color="white" />
      <ThresholdPreviewBand
        label="Medium"
        width={values.high - values.medium}
        background="var(--color-sentinel-amber)"
        color="#111827"
      />
      <ThresholdPreviewBand
        label="High"
        width={values.critical - values.high}
        background="var(--color-sentinel-amber)"
        color="white"
      />
      <ThresholdPreviewBand
        label="Critical"
        width={100 - values.critical}
        background="var(--color-sentinel-red)"
        color="white"
      />
    </div>
  );
}

function ThresholdPreviewBand({
  label,
  width,
  background,
  color,
}: {
  label: string;
  width: number;
  background: string;
  color: string;
}) {
  return (
    <div
      className="flex items-center justify-center text-xs font-medium"
      style={{ width: `${width}%`, background, color }}
    >
      {label}
    </div>
  );
}

function ThresholdSaveAction({
  isSaving,
  onSave,
}: {
  isSaving: boolean;
  onSave: () => void;
}) {
  return (
    <div className="mt-4 flex items-center justify-end gap-3">
      <button
        type="button"
        onClick={onSave}
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
  );
}

function ThresholdInputGrid({
  values,
  onMediumChange,
  onHighChange,
  onCriticalChange,
}: {
  values: RiskThresholdValues;
  onMediumChange: (value: number) => void;
  onHighChange: (value: number) => void;
  onCriticalChange: (value: number) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <ThresholdInputCard
        label="Medium Threshold"
        value={values.medium}
        description={`Scores below ${values.medium} stay low`}
        onChange={onMediumChange}
      />
      <ThresholdInputCard
        label="High Threshold"
        value={values.high}
        description={`Scores ${values.medium}-${values.high - 1} render as medium`}
        onChange={onHighChange}
      />
      <ThresholdInputCard
        label="Critical Threshold"
        value={values.critical}
        description={`Scores ${values.critical}+ render as critical`}
        onChange={onCriticalChange}
      />
    </div>
  );
}

export function RiskThresholdEditor({ medium, high, critical, onSave }: RiskThresholdEditorProps) {
  const [mediumValue, setMediumValue] = useState(medium);
  const [highValue, setHighValue] = useState(high);
  const [criticalValue, setCriticalValue] = useState(critical);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const values = { medium: mediumValue, high: highValue, critical: criticalValue };

  useEffect(() => {
    setMediumValue(medium);
    setHighValue(high);
    setCriticalValue(critical);
  }, [medium, high, critical]);

  const handleSave = async () => {
    const error = validateRiskThresholds(values);
    setValidationError(error);
    if (error) {
      return;
    }

    setIsSaving(true);
    try {
      await onSave(values);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <ThresholdValidationError message={validationError} />
      <ThresholdInputGrid
        values={values}
        onMediumChange={setMediumValue}
        onHighChange={setHighValue}
        onCriticalChange={setCriticalValue}
      />
      <ThresholdPreview values={values} isSaving={isSaving} onSave={handleSave} />
    </div>
  );
}

export default RiskThresholdEditor;
