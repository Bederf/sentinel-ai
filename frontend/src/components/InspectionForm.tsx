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

  const handleResponseChange = (itemId: string, value: any) => {
    setResponses((prev) => ({
      ...prev,
      [itemId]: {
        value,
        measured_at: new Date().toISOString(),
      },
    }));
  };

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

  const isWithinTolerance = (item: ChecklistItemDef, value: number): boolean | null => {
    if (item.tolerance_min === undefined || item.tolerance_max === undefined) {
      return null;
    }
    return value >= item.tolerance_min && value <= item.tolerance_max;
  };

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

  const panelStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
    padding: 16,
  };

  const cardStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
  };

  if (loading) {
    return (
      <div className="space-y-4 p-4">
        <div className="animate-pulse" style={cardStyle}>
          <div className="h-8 bg-gray-200 rounded w-2/3 mb-4" style={cardStyle}></div>
          <div className="space-y-3">
            <div className="h-12 bg-gray-200 rounded"></div>
            <div className="h-12 bg-gray-200 rounded"></div>
            <div className="h-12 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error && !template) {
    return (
      <div className="p-4">
        <div style={cardStyle}>
          <div className="flex items-center gap-2 mb-4" style={{ color: "var(--color-sentinel-red)" }}>
            <AlertTriangle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          {onCancel && (
            <button
              onClick={onCancel}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <ArrowLeft className="h-4 w-4" />
              Go Back
            </button>
          )}
        </div>
      </div>
    );
  }

  if (!template) {
    return null;
  }

  return (
    <div className="space-y-4 pb-24">
      <div style={cardStyle}>
        <div className="flex items-start justify-between p-4">
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {template.template_name}
            </h2>
            {equipmentName && (
              <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{equipmentName}</p>
            )}
          </div>
          {onCancel && (
            <button
              onClick={onCancel}
              className="inline-flex items-center p-1.5 rounded-md transition-colors"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-4 px-4 pb-2 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            <span>~{template.estimated_duration_minutes} min</span>
          </div>
          <div className="flex items-center gap-1">
            <ClipboardList className="h-4 w-4" />
            <span>{template.checklist_items.length} items</span>
          </div>
        </div>

        <div className="p-4 pt-2">
          <div className="flex items-center justify-between text-sm mb-1">
            <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Progress</span>
            <span className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {progress.completed}/{progress.total} ({progress.percent}%)
            </span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <div
              className="h-full transition-all duration-300"
              style={{ width: `${progress.percent}%`, background: "var(--color-sentinel-blue)" }}
            />
          </div>
        </div>
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
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {Object.entries(groupedItems).map(([category, items]) => (
        <div key={category} style={cardStyle}>
          <div className="p-4">
            <h3 className="text-base font-medium mb-4" style={{ color: "var(--color-sentinel-text-primary)" }}>{category}</h3>

            <div className="space-y-4">
              {items.map((item) => (
                <div key={item.item_id} className="space-y-2">
                  <div className="flex items-start justify-between">
                    <label className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {item.question}
                      {item.required && <span className="text-red-500 ml-1">*</span>}
                    </label>
                    {responses[item.item_id]?.value && (
                      <CheckCircle className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-green)" }} />
                    )}
                  </div>

                  {item.item_type === 'checklist' && item.options && (
                    <select
                      value={responses[item.item_id]?.value || ''}
                      onChange={(event) => handleResponseChange(item.item_id, event.target.value)}
                      className="w-full rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                        color: "var(--color-sentinel-text-primary)",
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

                  {item.item_type === 'measurement' && (
                    <div className="space-y-1">
                      <div className="flex gap-2 items-center">
                        <input
                          type="number"
                          placeholder={`Enter value (${item.unit || ''})`}
                          value={responses[item.item_id]?.value || ''}
                          onChange={(e) => handleResponseChange(item.item_id, parseFloat(e.target.value))}
                          className="flex-1 rounded-md px-3 py-2 text-sm"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            border: "1px solid var(--color-sentinel-border)",
                            color: "var(--color-sentinel-text-primary)",
                            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                            outline: "none",
                          }}
                        />
                        {item.photos_required && (
                          <button
                            onClick={() => handlePhotoAdd(item.item_id)}
                            className="inline-flex items-center p-1.5 rounded-md transition-colors"
                            style={{
                              background: "var(--color-sentinel-bg-secondary)",
                              border: "1px solid var(--color-sentinel-border)",
                              color: "var(--color-sentinel-text-primary)",
                            }}
                          >
                            <Camera className="h-4 w-4" />
                          </button>
                        )}
                      </div>

                      {item.tolerance_min !== undefined &&
                        item.tolerance_max !== undefined && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                              Range: {item.tolerance_min} - {item.tolerance_max} {item.unit}
                            </span>
                            {responses[item.item_id]?.value !== undefined && (
                              <span
                                className="inline-flex items-center px-1.5 py-0.5 text-xs font-medium rounded-full"
                                style={{
                                  background: isWithinTolerance(item, responses[item.item_id].value)
                                    ? "rgba(16,185,129,0.15)"
                                    : "rgba(220,38,38,0.15)",
                                  color: isWithinTolerance(item, responses[item.item_id].value)
                                    ? "var(--color-sentinel-green)"
                                    : "var(--color-sentinel-red)",
                                }}
                              >
                                {isWithinTolerance(item, responses[item.item_id].value) ? 'OK' : 'Out of range'}
                              </span>
                            )}
                          </div>
                        )}
                    </div>
                  )}

                  {item.item_type === 'visual_inspection' && (
                    <div className="space-y-2">
                      <input
                        type="text"
                        placeholder="Enter observations"
                        value={responses[item.item_id]?.value || ''}
                        onChange={(e) => handleResponseChange(item.item_id, e.target.value)}
                        className="w-full rounded-md px-3 py-2 text-sm"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          border: "1px solid var(--color-sentinel-border)",
                          color: "var(--color-sentinel-text-primary)",
                          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                          outline: "none",
                        }}
                      />
                      {item.photos_required && (
                        <button
                          onClick={() => handlePhotoAdd(item.item_id)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors"
                          style={{
                            background: "var(--color-sentinel-bg-secondary)",
                            border: "1px solid var(--color-sentinel-border)",
                            color: "var(--color-sentinel-text-primary)",
                          }}
                        >
                          <Camera className="h-4 w-4" />
                          Add Photo
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}

      <div style={cardStyle}>
        <div className="p-4">
          <label className="text-sm font-medium block mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Additional Notes (optional)
          </label>
          <input
            type="text"
            placeholder="Any additional observations or comments"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full rounded-md px-3 py-2 text-sm"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
              outline: "none",
            }}
          />
        </div>
      </div>

      {photos.length > 0 && (
        <div style={cardStyle}>
          <div className="p-4">
            <h3 className="text-sm font-medium mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Photos Attached ({photos.length})
            </h3>
            <div className="flex flex-wrap gap-2">
              {photos.map((photo, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full"
                  style={{
                    background: "rgba(59,130,246,0.15)",
                    color: "var(--color-sentinel-blue)",
                  }}
                >
                  {photo.file_name}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      <div
        className="fixed bottom-0 left-0 right-0 p-4"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          borderTop: "1px solid var(--color-sentinel-border)",
        }}
      >
        <button
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
          onClick={handleSubmit}
          disabled={submitting || progress.percent === 0}
          style={{
            background: "var(--color-sentinel-blue)",
            border: "1px solid var(--color-sentinel-blue)",
            color: "#fff",
          }}
        >
          {submitting ? (
            <>
              <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              Submitting...
            </>
          ) : (
            <>
              <Save className="h-5 w-5" />
              Submit Inspection ({progress.percent}% complete)
            </>
          )}
        </button>
      </div>
    </div>
  );
}
