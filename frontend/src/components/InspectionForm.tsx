/**
 * InspectionForm - Mobile-optimized inspection submission form
 *
 * Features:
 * - Loads checklist template for equipment type
 * - Grouped items by category
 * - Supports checklist, measurement, and visual inspection items
 * - Photo capture for items requiring photos
 * - Tolerance display for measurements
 * - Progress tracking
 * - Mobile-friendly with large touch targets
 *
 * Part of Phase 55: Routine Inspection & Maintenance
 */

import { useState, useEffect } from 'react';

import {
  Camera,
  Save,
  CheckCircle,
  AlertTriangle,
  ArrowLeft,
  ClipboardList,
  Clock,
} from 'lucide-react';
import {
  inspectionApi,
  type ChecklistTemplateItem,
  type ChecklistItemDef,
  type InspectionSubmissionRequest,
  type InspectionPhotoAttachment,
  type InspectionTaskItem,
} from '@/lib/api';

interface InspectionFormProps {
  equipmentId: string;
  equipmentType: string;
  equipmentName?: string;
  onComplete?: (task: InspectionTaskItem) => void;
  onCancel?: () => void;
}

export default function InspectionForm({
  equipmentId,
  equipmentType,
  equipmentName,
  onComplete,
  onCancel,
}: InspectionFormProps) {
  const [template, setTemplate] = useState<ChecklistTemplateItem | null>(null);
  const [responses, setResponses] = useState<Record<string, any>>({});
  const [photos, setPhotos] = useState<InspectionPhotoAttachment[]>([]);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startTime] = useState<Date>(new Date());

  // Load template on mount
  useEffect(() => {
    async function loadTemplate() {
      setLoading(true);
      setError(null);

      try {
        const templateData = await inspectionApi.getChecklistTemplate(
          equipmentType,
          'routine'
        );
        setTemplate(templateData);
      } catch (err) {
        console.error('Failed to load template:', err);
        setError(err instanceof Error ? err.message : 'Failed to load template');
      } finally {
        setLoading(false);
      }
    }

    loadTemplate();
  }, [equipmentType]);

  // Handle response changes
  const handleResponseChange = (itemId: string, value: any) => {
    setResponses((prev) => ({
      ...prev,
      [itemId]: {
        value,
        measured_at: new Date().toISOString(),
      },
    }));
  };

  // Handle photo addition via file input
  const handlePhotoAdd = (itemId: string) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const fileUrl = URL.createObjectURL(file);
        setPhotos((prev) => [
          ...prev,
          {
            file_url: fileUrl,
            file_name: file.name,
            description: `Photo for ${itemId}`,
            element_id: itemId,
          },
        ]);
      }
    };
    input.click();
  };

  // Calculate completion progress
  const getCompletionProgress = (): { completed: number; total: number; percent: number } => {
    if (!template) return { completed: 0, total: 0, percent: 0 };

    const total = template.checklist_items.length;
    const completed = Object.keys(responses).filter((key) => {
      const response = responses[key];
      return response && (response.value !== undefined && response.value !== '');
    }).length;

    return {
      completed,
      total,
      percent: total > 0 ? Math.round((completed / total) * 100) : 0,
    };
  };

  // Check if measurement is within tolerance
  const isWithinTolerance = (item: ChecklistItemDef, value: number): boolean | null => {
    if (item.tolerance_min === undefined || item.tolerance_max === undefined) {
      return null;
    }
    return value >= item.tolerance_min && value <= item.tolerance_max;
  };

  // Handle form submission
  const handleSubmit = async () => {
    if (!template) return;

    setSubmitting(true);
    setError(null);

    try {
      const durationMinutes = Math.round(
        (new Date().getTime() - startTime.getTime()) / 60000
      );

      const submission: InspectionSubmissionRequest = {
        equipment_id: equipmentId,
        template_id: template.template_id,
        checklist_responses: responses,
        photos,
        duration_minutes: durationMinutes,
        notes: notes || undefined,
      };

      const task = await inspectionApi.submitInspection(submission);

      if (onComplete) {
        onComplete(task);
      }
    } catch (err) {
      console.error('Failed to submit inspection:', err);
      setError(err instanceof Error ? err.message : 'Failed to submit inspection');
    } finally {
      setSubmitting(false);
    }
  };

  // Group items by category
  const groupedItems = template
    ? template.checklist_items.reduce(
        (acc, item) => {
          const category = item.category || 'General';
          if (!acc[category]) {
            acc[category] = [];
          }
          acc[category].push(item);
          return acc;
        },
        {} as Record<string, ChecklistItemDef[]>
      )
    : {};

  const progress = getCompletionProgress();

  if (loading) {
    return (
      <div className="space-y-4 p-4">
        <Card className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-2/3 mb-4"></div>
          <div className="space-y-3">
            <div className="h-12 bg-gray-200 rounded"></div>
            <div className="h-12 bg-gray-200 rounded"></div>
            <div className="h-12 bg-gray-200 rounded"></div>
          </div>
        </Card>
      </div>
    );
  }

  if (error && !template) {
    return (
      <div className="p-4">
        <Card>
          <div className="flex items-center gap-2 text-red-600 mb-4">
            <AlertTriangle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          {onCancel && (
            <Button variant="secondary" onClick={onCancel}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Go Back
            </Button>
          )}
        </Card>
      </div>
    );
  }

  if (!template) {
    return null;
  }

  return (
    <div className="space-y-4 pb-24">
      {/* Header */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {template.template_name}
            </h2>
            {equipmentName && (
              <p className="text-sm text-gray-500">{equipmentName}</p>
            )}
          </div>
          {onCancel && (
            <Button variant="light" size="xs" onClick={onCancel}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}
        </div>

        <div className="flex items-center gap-4 mt-3 text-sm text-gray-500">
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            <span>~{template.estimated_duration_minutes} min</span>
          </div>
          <div className="flex items-center gap-1">
            <ClipboardList className="h-4 w-4" />
            <span>{template.checklist_items.length} items</span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between text-sm mb-1">
            <span className="text-gray-500">Progress</span>
            <span className="font-medium">
              {progress.completed}/{progress.total} ({progress.percent}%)
            </span>
          </div>
          <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>
      </Card>

      {/* Error Display */}
      {error && (
        <Card className="bg-red-50 border-red-200">
          <div className="flex items-center gap-2 text-red-700">
            <AlertTriangle className="h-5 w-5" />
            <span>{error}</span>
          </div>
        </Card>
      )}

      {/* Checklist Items by Category */}
      {Object.entries(groupedItems).map(([category, items]) => (
        <Card key={category}>
          <h3 className="text-base font-medium text-gray-900 mb-4">{category}</h3>

          <div className="space-y-4">
            {items.map((item) => (
              <div key={item.item_id} className="space-y-2">
                <div className="flex items-start justify-between">
                  <label className="text-sm font-medium text-gray-700">
                    {item.question}
                    {item.required && <span className="text-red-500 ml-1">*</span>}
                  </label>
                  {responses[item.item_id]?.value && (
                    <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                  )}
                </div>

                {/* Checklist Item (Multiple Choice) */}
                {item.item_type === 'checklist' && item.options && (
                  <select
                    value={responses[item.item_id]?.value || ''}
                    onChange={(event) => handleResponseChange(item.item_id, event.target.value)}
                    className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                    style={{
                      background: "var(--color-grafana-bg-secondary)",
                      border: "1px solid var(--color-grafana-border)",
                      color: "var(--color-grafana-text-primary)",
                      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                      outline: "none",
                    }}
                    aria-label={`Select option for ${item.question}`}
                  >
                    <option value="">Select option</option>
                    {item.options.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                )}

                {/* Measurement Item (Numerical) */}
                {item.item_type === 'measurement' && (
                  <div className="space-y-1">
                    <div className="flex gap-2 items-center">
                      <NumberInput
                        placeholder={`Enter value (${item.unit || ''})`}
                        value={responses[item.item_id]?.value || ''}
                        onValueChange={(value: number) =>
                          handleResponseChange(item.item_id, value)
                        }
                        className="flex-1"
                      />
                      {item.photos_required && (
                        <Button
                          variant="secondary"
                          size="xs"
                          onClick={() => handlePhotoAdd(item.item_id)}
                        >
                          <Camera className="h-4 w-4" />
                        </Button>
                      )}
                    </div>

                    {/* Tolerance Display */}
                    {item.tolerance_min !== undefined &&
                      item.tolerance_max !== undefined && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-500">
                            Range: {item.tolerance_min} - {item.tolerance_max} {item.unit}
                          </span>
                          {responses[item.item_id]?.value !== undefined && (
                            <Badge
                              color={
                                isWithinTolerance(
                                  item,
                                  responses[item.item_id].value
                                )
                                  ? 'green'
                                  : 'red'
                              }
                              size="xs"
                            >
                              {isWithinTolerance(item, responses[item.item_id].value)
                                ? 'OK'
                                : 'Out of range'}
                            </Badge>
                          )}
                        </div>
                      )}
                  </div>
                )}

                {/* Visual Inspection Item (Text + Photo) */}
                {item.item_type === 'visual_inspection' && (
                  <div className="space-y-2">
                    <TextInput
                      placeholder="Enter observations"
                      value={responses[item.item_id]?.value || ''}
                      onChange={(e) =>
                        handleResponseChange(item.item_id, e.target.value)
                      }
                    />
                    {item.photos_required && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handlePhotoAdd(item.item_id)}
                      >
                        <Camera className="h-4 w-4 mr-2" />
                        Add Photo
                      </Button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      ))}

      {/* Notes Section */}
      <Card>
        <label className="text-sm font-medium text-gray-700 block mb-2">
          Additional Notes (optional)
        </label>
        <TextInput
          placeholder="Any additional observations or comments"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </Card>

      {/* Photo Attachments Summary */}
      {photos.length > 0 && (
        <Card>
          <h3 className="text-sm font-medium text-gray-900 mb-2">
            Photos Attached ({photos.length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {photos.map((photo, idx) => (
              <Badge key={idx} color="blue" size="xs">
                {photo.file_name}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Submit Button - Fixed at bottom on mobile */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-white border-t shadow-lg">
        <Button
          size="lg"
          className="w-full"
          onClick={handleSubmit}
          disabled={submitting || progress.percent === 0}
        >
          {submitting ? (
            <>
              <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full mr-2" />
              Submitting...
            </>
          ) : (
            <>
              <Save className="h-5 w-5 mr-2" />
              Submit Inspection ({progress.percent}% complete)
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
