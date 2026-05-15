import { useState, useEffect } from 'react';

import { CheckCircle2, XCircle } from 'lucide-react';
import type { ColumnMapping } from '@/lib/api';

interface FormatDetectionResult {
  file_format: 'csv' | 'excel' | 'json';
  delimiter: string;
  vendor: string;
  confidence: number;
  suggested_mappings: Record<string, string>;
  row_count: number;
  sample_data?: Array<Record<string, any>>;
}

interface ColumnMappingStepProps {
  siteId: string;
  formatDetection: FormatDetectionResult;
  onNext: (data: { columnMappings: ColumnMapping[] }) => void;
  onBack: () => void;
}

const SENTINEL_FIELDS = [
  { value: 'timestamp', label: 'Timestamp', required: true },
  { value: 'point_id', label: 'Point ID', required: true },
  { value: 'point_name', label: 'Point Name', required: false },
  { value: 'alarm_code', label: 'Alarm Code', required: false },
  { value: 'alarm_state', label: 'Alarm State', required: false },
  { value: 'severity', label: 'Severity', required: false },
  { value: 'value', label: 'Value', required: false },
  { value: 'unit', label: 'Unit', required: false },
  { value: 'description', label: 'Description', required: false },
  { value: 'ignore', label: 'Ignore Column', required: false }
];

const TRANSFORM_TYPES = [
  { value: 'none', label: 'None' },
  { value: 'date_parse', label: 'Parse Date' },
  { value: 'number_parse', label: 'Parse Number' },
  { value: 'boolean_parse', label: 'Parse Boolean' }
];

export function ColumnMappingStep({ siteId: _siteId, formatDetection, onNext, onBack }: ColumnMappingStepProps) {
  const [mappings, setMappings] = useState<Record<string, { target_field: string; transform_type: string }>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (formatDetection?.suggested_mappings) {
      const initial: Record<string, { target_field: string; transform_type: string }> = {};
      Object.entries(formatDetection.suggested_mappings).forEach(([source, target]) => {
        initial[source] = {
          target_field: target,
          transform_type: target === 'timestamp' ? 'date_parse' : 'none'
        };
      });
      setMappings(initial);
    }
  }, [formatDetection]);

  const sourceColumns = Object.keys(formatDetection?.suggested_mappings || {});

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      const hasTimestamp = Object.values(mappings).some(m => m.target_field === 'timestamp');
      const hasPointId = Object.values(mappings).some(m => m.target_field === 'point_id');

      if (!hasTimestamp || !hasPointId) {
        throw new Error('Timestamp and Point ID are required fields');
      }

      const columnMappings: ColumnMapping[] = Object.entries(mappings)
        .filter(([_, config]) => config.target_field !== 'ignore')
        .map(([source_column, config]) => ({
          source_column,
          target_field: config.target_field,
          transform_type: config.transform_type as 'none' | 'date_parse' | 'number_parse' | 'boolean_parse'
        }));

      onNext({ columnMappings });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Map Columns
        </h3>
        <p className="mt-2 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Confirm or adjust the auto-detected column mappings. Required fields: Timestamp, Point ID.
        </p>
      </div>

      <div
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <table className="w-full">
          <thead>
            <tr
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                borderBottom: "1px solid var(--color-sentinel-border)",
              }}
            >
              <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>Source Column</th>
              <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>SENTINEL Field</th>
              <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>Transform</th>
              <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {sourceColumns.map((source) => {
              const mapping = mappings[source];
              const field = SENTINEL_FIELDS.find(f => f.value === mapping?.target_field);
              const isRequired = field?.required;

              return (
                <tr key={source} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>{source}</span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={mapping?.target_field || 'ignore'}
                      onChange={(event) => {
                        const value = event.target.value;
                        setMappings({
                          ...mappings,
                          [source]: {
                            ...mappings[source],
                            target_field: value,
                            transform_type: value === 'timestamp' ? 'date_parse' : 'none'
                          }
                        });
                      }}
                      className="w-48 rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                      style={{
                        background: "var(--color-grafana-bg-secondary)",
                        border: "1px solid var(--color-grafana-border)",
                        color: "var(--color-grafana-text-primary)",
                        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                        outline: "none",
                      }}
                      aria-label={`Map ${source} field`}
                    >
                      {SENTINEL_FIELDS.map(field => (
                        <option key={field.value} value={field.value}>
                          {field.required ? `${field.label} *` : field.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    {mapping?.target_field && mapping?.target_field !== 'ignore' && (
                      <select
                        value={mapping?.transform_type || 'none'}
                        onChange={(event) => {
                          const value = event.target.value;
                          setMappings({
                            ...mappings,
                            [source]: {
                              ...mappings[source],
                              transform_type: value
                            }
                          });
                        }}
                        className="w-36 rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                        style={{
                          background: "var(--color-grafana-bg-secondary)",
                          border: "1px solid var(--color-grafana-border)",
                          color: "var(--color-grafana-text-primary)",
                          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                          outline: "none",
                        }}
                        aria-label={`Select transform for ${source}`}
                      >
                        {TRANSFORM_TYPES.map(type => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {mapping?.target_field === 'ignore' && (
                      <XCircle className="w-5 h-5 text-gray-400" />
                    )}
                    {mapping?.target_field && mapping?.target_field !== 'ignore' && (
                      <CheckCircle2 className={`w-5 h-5 ${isRequired ? 'text-green-500' : 'text-blue-500'}`} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {error && (
        <div
          className="p-3 rounded-md text-sm flex items-center gap-2"
          style={{
            background: "rgba(220,38,38,0.15)",
            border: "1px solid rgba(220,38,38,0.3)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <span className="font-medium">Error</span>
          <span>{error}</span>
        </div>
      )}

      <div className="flex items-center gap-2 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        <CheckCircle2 className="w-4 h-4" />
        <span>
          {Object.values(mappings).filter(m => m.target_field !== 'ignore').length} of {sourceColumns.length} columns mapped
        </span>
      </div>

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="px-4 py-2 text-sm font-medium rounded-md transition-colors"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          }}
        >
          Back
        </button>

        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
          style={{
            background: "var(--color-sentinel-blue)",
            border: "1px solid var(--color-sentinel-blue)",
            color: "#fff",
          }}
        >
          {saving ? 'Saving...' : 'Next: Match Points'}
        </button>
      </div>
    </div>
  );
}
