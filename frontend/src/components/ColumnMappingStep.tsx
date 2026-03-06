// ColumnMappingStep.tsx
import { useState, useEffect } from 'react';
import { Button, Card, Callout, Select, SelectItem, Table, TableBody, TableCell, TableHead, TableRow, Text, Title } from '@tremor/react';
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

  // Initialize from suggested mappings
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
      // Validate required fields
      const hasTimestamp = Object.values(mappings).some(m => m.target_field === 'timestamp');
      const hasPointId = Object.values(mappings).some(m => m.target_field === 'point_id');

      if (!hasTimestamp || !hasPointId) {
        throw new Error('Timestamp and Point ID are required fields');
      }

      // Convert to array
      const columnMappings: ColumnMapping[] = Object.entries(mappings)
        .filter(([_, config]) => config.target_field !== 'ignore')
        .map(([source_column, config]) => ({
          source_column,
          target_field: config.target_field,
          transform_type: config.transform_type as 'none' | 'date_parse' | 'number_parse' | 'boolean_parse'
        }));

      // Note: In the full implementation, we would need a log_source_id
      // For now, we pass the mappings to the next step
      // TODO: Create log source or use existing log_source_id from formatDetection
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
        <Title>Map Columns</Title>
        <Text className="mt-2">
          Confirm or adjust the auto-detected column mappings. Required fields: Timestamp, Point ID.
        </Text>
      </div>

      {/* Mapping table */}
      <Card>
        <Table>
          <TableHead>
            <TableRow>
              <TableHead>Source Column</TableHead>
              <TableHead>SENTINEL Field</TableHead>
              <TableHead>Transform</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHead>
          <TableBody>
            {sourceColumns.map((source) => {
              const mapping = mappings[source];
              const field = SENTINEL_FIELDS.find(f => f.value === mapping?.target_field);
              const isRequired = field?.required;

              return (
                <TableRow key={source}>
                  <TableCell>
                    <span className="font-mono text-sm">{source}</span>
                  </TableCell>
                  <TableCell>
                    <Select
                      value={mapping?.target_field || 'ignore'}
                      onValueChange={(value) => {
                        setMappings({
                          ...mappings,
                          [source]: {
                            ...mappings[source],
                            target_field: value,
                            transform_type: value === 'timestamp' ? 'date_parse' : 'none'
                          }
                        });
                      }}
                      className="w-48"
                    >
                      {SENTINEL_FIELDS.map(field => (
                        <SelectItem key={field.value} value={field.value}>
                          {field.label}
                          {field.required && <span className="text-red-500 ml-1">*</span>}
                        </SelectItem>
                      ))}
                    </Select>
                  </TableCell>
                  <TableCell>
                    {mapping?.target_field && mapping?.target_field !== 'ignore' && (
                      <Select
                        value={mapping?.transform_type || 'none'}
                        onValueChange={(value) => {
                          setMappings({
                            ...mappings,
                            [source]: {
                              ...mappings[source],
                              transform_type: value
                            }
                          });
                        }}
                        className="w-36"
                      >
                        {TRANSFORM_TYPES.map(type => (
                          <SelectItem key={type.value} value={type.value}>
                            {type.label}
                          </SelectItem>
                        ))}
                      </Select>
                    )}
                  </TableCell>
                  <TableCell>
                    {mapping?.target_field === 'ignore' && (
                      <XCircle className="w-5 h-5 text-gray-400" />
                    )}
                    {mapping?.target_field && mapping?.target_field !== 'ignore' && (
                      <CheckCircle2 className={`w-5 h-5 ${isRequired ? 'text-green-500' : 'text-blue-500'}`} />
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      {/* Validation status */}
      {error && (
        <Callout title="Error" color="rose">{error}</Callout>
      )}

      <div className="flex items-center gap-2 text-sm text-gray-600">
        <CheckCircle2 className="w-4 h-4" />
        <span>
          {Object.values(mappings).filter(m => m.target_field !== 'ignore').length} of {sourceColumns.length} columns mapped
        </span>
      </div>

      {/* Actions */}
      <div className="flex justify-between">
        <Button onClick={onBack} variant="secondary" color="gray">
          Back
        </Button>

        <Button
          onClick={handleSave}
          disabled={saving}
          color="blue"
        >
          {saving ? 'Saving...' : 'Next: Match Points'}
        </Button>
      </div>
    </div>
  );
}
