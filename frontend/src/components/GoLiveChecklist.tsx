/**
 * GoLiveChecklist Component
 *
 * Displays validation checklist for building go-live activation.
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useCallback } from "react";
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Circle,
  Loader2,
  Play,
  Power,
  RefreshCw,
} from "lucide-react";

import { validationApi } from '@/lib/api';
import { formatDateTime } from "../lib/timeFormat";
import type {
  ValidationChecklist,
  ChecklistItem,
  BuildingStatus,
  ActivationResult,
} from '@/lib/api';

interface GoLiveChecklistProps {
  siteId: string;
  onStatusChange?: (status: BuildingStatus) => void;
}

const statusBadgeStyles: Record<BuildingStatus, { bg: string; color: string }> = {
  draft: { bg: "rgba(142,142,142,0.15)", color: "var(--color-sentinel-text-secondary)" },
  pending_validation: { bg: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)" },
  active: { bg: "rgba(16,185,129,0.15)", color: "var(--color-sentinel-green)" },
  suspended: { bg: "rgba(220,38,38,0.15)", color: "var(--color-sentinel-red)" },
};

function StatusBadge({ status }: { status: BuildingStatus }) {
  const style = statusBadgeStyles[status];
  const labels: Record<BuildingStatus, string> = {
    draft: "Draft",
    pending_validation: "Pending Validation",
    active: "Active",
    suspended: "Suspended",
  };

  return (
    <span
      className="inline-flex items-center px-3 py-1 text-sm font-medium rounded-full"
      style={{ background: style.bg, color: style.color }}
    >
      {labels[status]}
    </span>
  );
}

function StatusIcon({ status }: { status: ChecklistItem["status"] }) {
  switch (status) {
    case "pass":
      return <CheckCircle className="w-5 h-5" style={{ color: "var(--color-sentinel-green)" }} />;
    case "fail":
      return <XCircle className="w-5 h-5" style={{ color: "var(--color-sentinel-red)" }} />;
    case "warning":
      return <AlertTriangle className="w-5 h-5" style={{ color: "var(--color-sentinel-amber)" }} />;
    case "not_checked":
    default:
      return <Circle className="w-5 h-5" style={{ color: "var(--color-sentinel-text-disabled)" }} />;
  }
}

function formatValue(value: any, threshold: any): string {
  if (value === undefined || value === null) return "";

  const valueStr = typeof value === "number"
    ? value % 1 === 0
      ? value.toString()
      : value.toFixed(1)
    : String(value);

  if (threshold === undefined || threshold === null) return valueStr;

  const thresholdStr = typeof threshold === "number"
    ? threshold % 1 === 0
      ? threshold.toString()
      : threshold.toFixed(1)
    : String(threshold);

  if (typeof value === "number" && value <= 100 && value >= 0) {
    return `${valueStr}% / ${thresholdStr}% required`;
  }

  return `${valueStr} / ${thresholdStr} required`;
}

function ConfirmationModal({
  isOpen,
  title,
  message,
  confirmText,
  cancelText,
  isLoading,
  onConfirm,
  onCancel,
}: {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
  isLoading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onCancel}
      />

      <div
        className="relative z-10 max-w-md w-full mx-4 p-6 rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <h3
          className="text-lg font-semibold mb-2"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          {title}
        </h3>
        <p
          className="text-sm mb-6"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          {message}
        </p>

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-green)",
              border: "1px solid var(--color-sentinel-green)",
              color: "#fff",
            }}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Processing...
              </>
            ) : (
              confirmText
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function groupByCategory(items: ChecklistItem[]): Record<string, ChecklistItem[]> {
  return items.reduce((acc, item) => {
    if (!acc[item.category]) {
      acc[item.category] = [];
    }
    acc[item.category].push(item);
    return acc;
  }, {} as Record<string, ChecklistItem[]>);
}

const categoryLabels: Record<string, string> = {
  data_source: "Data Sources",
  point_mapping: "Point Mapping",
  data_quality: "Data Quality",
  configuration: "Configuration",
};

export function GoLiveChecklist({ siteId, onStatusChange }: GoLiveChecklistProps) {
  const [checklist, setChecklist] = useState<ValidationChecklist | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isValidating, setIsValidating] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activationResult, setActivationResult] = useState<ActivationResult | null>(null);

  const fetchChecklist = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const data = await validationApi.getChecklist(siteId);
      setChecklist(data);
    } catch (err: any) {
      if (err?.status === 429) {
        console.warn("Rate limited, retrying in 3 seconds...");
        await new Promise((resolve) => setTimeout(resolve, 3000));
        try {
          const data = await validationApi.getChecklist(siteId);
          setChecklist(data);
        } catch (retryErr) {
          console.error("Retry failed:", retryErr);
          setError("System temporarily overloaded. Please try again in a moment.");
        }
      } else {
        console.error("Failed to fetch checklist:", err);
        setError("Failed to load validation checklist");
      }
    } finally {
      setIsLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchChecklist();
  }, [fetchChecklist]);

  const handleValidate = async () => {
    setIsValidating(true);
    setError(null);
    setActivationResult(null);

    try {
      const data = await validationApi.validate(siteId);
      setChecklist(data);
      onStatusChange?.(data.status);
    } catch (err) {
      console.error("Validation failed:", err);
      setError("Failed to run validation");
    } finally {
      setIsValidating(false);
    }
  };

  const handleActivate = async () => {
    setIsActivating(true);
    setError(null);

    try {
      const result = await validationApi.activate(siteId);
      setActivationResult(result);
      setShowConfirmModal(false);

      if (result.success) {
        await fetchChecklist();
        onStatusChange?.(result.new_status);
      }
    } catch (err: any) {
      console.error("Activation failed:", err);
      setError(err.message || "Failed to activate building");
      setShowConfirmModal(false);
    } finally {
      setIsActivating(false);
    }
  };

  const groupedItems = checklist ? groupByCategory(checklist.items) : {};

  const cardStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-panel)",
    border: "1px solid var(--color-sentinel-border)",
    borderRadius: 8,
  };

  if (isLoading) {
    return (
      <div style={{ ...cardStyle, padding: 24 }}>
        <div className="flex items-center justify-center py-8">
          <Loader2
            className="w-8 h-8 animate-spin"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          />
          <span
            className="ml-3"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Loading validation checklist...
          </span>
        </div>
      </div>
    );
  }

  if (error && !checklist) {
    return (
      <div style={{ ...cardStyle, padding: 24 }}>
        <div
          className="p-3 rounded-md text-sm"
          style={{
            background: "rgba(220,38,38,0.15)",
            border: "1px solid rgba(220,38,38,0.3)",
            color: "var(--color-sentinel-red)",
          }}
        >
          <div>{error}</div>
          <button
            onClick={fetchChecklist}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors mt-4"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!checklist) {
    return null;
  }

  return (
    <>
      <div className="overflow-hidden" style={cardStyle}>
        <div
          className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div>
              <h3
                className="font-semibold text-base"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {checklist.site_name || `Building ${siteId}`}
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={checklist.status} />
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                >
                  Last checked: {formatDateTime(checklist.checked_at)}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleValidate}
              disabled={isValidating}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {isValidating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Validating...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Run Validation
                </>
              )}
            </button>

            <button
              onClick={() => setShowConfirmModal(true)}
              disabled={!checklist.can_activate || isValidating}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors disabled:opacity-50"
              style={{
                background: checklist.can_activate ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-green)",
                color: checklist.can_activate ? "#fff" : "var(--color-sentinel-text-disabled)",
              }}
            >
              <Power className="w-4 h-4" />
              Activate
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4">
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
          </div>
        )}

        {activationResult?.success && (
          <div className="p-4">
            <div
              className="p-3 rounded-md text-sm flex items-center gap-2"
              style={{
                background: "rgba(16,185,129,0.15)",
                border: "1px solid rgba(16,185,129,0.3)",
                color: "var(--color-sentinel-green)",
              }}
            >
              <span className="font-medium">Success</span>
              <span>{activationResult.message}</span>
            </div>
          </div>
        )}

        <div className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(groupedItems).map(([category, items]) => (
              <div
                key={category}
                className="rounded-md p-4"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
              >
                <h4
                  className="font-medium text-sm mb-3 uppercase tracking-wide"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {categoryLabels[category] || category}
                </h4>

                <div className="space-y-3">
                  {items.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-3"
                    >
                      <StatusIcon status={item.status} />
                      <div className="flex-1 min-w-0">
                        <div
                          className="font-medium text-sm"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {item.name}
                        </div>
                        <div
                          className="text-xs mt-0.5"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {item.description}
                        </div>

                        {(item.value !== undefined || item.threshold !== undefined) && (
                          <div
                            className="text-xs mt-1 font-mono"
                            style={{
                              color:
                                item.status === "pass"
                                  ? "var(--color-sentinel-green)"
                                  : item.status === "fail"
                                  ? "var(--color-sentinel-red)"
                                  : "var(--color-sentinel-amber)",
                            }}
                          >
                            {formatValue(item.value, item.threshold)}
                          </div>
                        )}

                        {item.details && (
                          <div
                            className="text-xs mt-1 italic"
                            style={{ color: "var(--color-sentinel-text-disabled)" }}
                          >
                            {item.details}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div
          className="p-4"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <span
              className="inline-flex items-center px-3 py-1 text-sm font-medium rounded-full"
              style={{ background: "rgba(16,185,129,0.15)", color: "var(--color-sentinel-green)" }}
            >
              {checklist.summary.passed} passed
            </span>
            <span
              className="inline-flex items-center px-3 py-1 text-sm font-medium rounded-full"
              style={{ background: "rgba(220,38,38,0.15)", color: "var(--color-sentinel-red)" }}
            >
              {checklist.summary.failed} failed
            </span>
            <span
              className="inline-flex items-center px-3 py-1 text-sm font-medium rounded-full"
              style={{ background: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)" }}
            >
              {checklist.summary.warnings} warnings
            </span>
          </div>

          {checklist.blocking_issues.length > 0 && (
            <div className="mb-4 p-3 rounded-md border" style={{ borderColor: "rgba(220,38,38,0.5)", background: "rgba(220,38,38,0.1)" }}>
              <div className="font-medium text-sm mb-2" style={{ color: "var(--color-sentinel-red)" }}>Blocking Issues</div>
              <div className="space-y-1">
                {checklist.blocking_issues.map((issue, index) => (
                  <div key={index} className="text-sm flex items-start gap-2" style={{ color: "var(--color-sentinel-red)", opacity: 0.8 }}>
                    <span className="flex-shrink-0" style={{ color: "var(--color-sentinel-red)" }}>•</span>
                    <span>{issue}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div
            className="text-sm"
            style={{
              color: checklist.can_activate
                ? "var(--color-sentinel-green)"
                : "var(--color-sentinel-text-secondary)",
            }}
          >
            {checklist.can_activate ? (
              <span className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />
                All critical checks passed. Building can be activated.
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <XCircle className="w-4 h-4" style={{ color: "var(--color-sentinel-red)" }} />
                Building cannot be activated until all critical issues are resolved.
              </span>
            )}
          </div>
        </div>
      </div>

      <ConfirmationModal
        isOpen={showConfirmModal}
        title="Activate Building"
        message={`Are you sure you want to activate "${checklist.site_name || siteId}"? This will enable live data collection and alerts for this building.`}
        confirmText="Activate"
        cancelText="Cancel"
        isLoading={isActivating}
        onConfirm={handleActivate}
        onCancel={() => setShowConfirmModal(false)}
      />
    </>
  );
}

export default GoLiveChecklist;
