/**
 * GoLiveChecklist Component
 *
 * Displays validation checklist for building go-live activation.
 * Features:
 * - Header with building status badge and action buttons
 * - Checklist grid with 4 categories
 * - Summary section with counts and blocking issues
 * - Activation flow with confirmation modal
 *
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
import { Card, Badge, Button, Callout } from "@tremor/react";
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

// Status badge component
function StatusBadge({ status }: { status: BuildingStatus }) {
  const statusStyles: Record<BuildingStatus, { color: "gray" | "yellow" | "green" | "red"; text: string }> = {
    draft: { color: "gray", text: "Draft" },
    pending_validation: { color: "yellow", text: "Pending Validation" },
    active: { color: "green", text: "Active" },
    suspended: { color: "red", text: "Suspended" },
  };

  const style = statusStyles[status];

  return (
    <Badge color={style.color} size="lg">
      {style.text}
    </Badge>
  );
}

// Checklist item status icon
function StatusIcon({ status }: { status: ChecklistItem["status"] }) {
  switch (status) {
    case "pass":
      return <CheckCircle className="w-5 h-5 text-green-500" />;
    case "fail":
      return <XCircle className="w-5 h-5 text-red-500" />;
    case "warning":
      return <AlertTriangle className="w-5 h-5 text-amber-500" />;
    case "not_checked":
    default:
      return <Circle className="w-5 h-5 text-gray-500" />;
  }
}

// Format value for display
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

  // Add % if it looks like a percentage
  if (typeof value === "number" && value <= 100 && value >= 0) {
    return `${valueStr}% / ${thresholdStr}% required`;
  }

  return `${valueStr} / ${thresholdStr} required`;
}

// Confirmation modal component
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
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onCancel}
      />

      {/* Modal */}
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
          <Button
            variant="secondary"
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelText}
          </Button>
          <Button
            onClick={onConfirm}
            disabled={isLoading}
            className="bg-green-600 hover:bg-green-700"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              confirmText
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Group checklist items by category
function groupByCategory(items: ChecklistItem[]): Record<string, ChecklistItem[]> {
  return items.reduce((acc, item) => {
    if (!acc[item.category]) {
      acc[item.category] = [];
    }
    acc[item.category].push(item);
    return acc;
  }, {} as Record<string, ChecklistItem[]>);
}

// Category display names
const categoryLabels: Record<string, string> = {
  data_source: "Data Sources",
  point_mapping: "Point Mapping",
  data_quality: "Data Quality",
  configuration: "Configuration",
};

export function GoLiveChecklist({ siteId, onStatusChange }: GoLiveChecklistProps) {
  // State
  const [checklist, setChecklist] = useState<ValidationChecklist | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isValidating, setIsValidating] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activationResult, setActivationResult] = useState<ActivationResult | null>(null);

  // Fetch checklist
  const fetchChecklist = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Add delay to stagger requests and avoid 429 rate limiting
      // Increased to 2s to prevent concurrent request bursts
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const data = await validationApi.getChecklist(siteId);
      setChecklist(data);
    } catch (err: any) {
      // Retry on rate limit with exponential backoff
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

  // Initial load
  useEffect(() => {
    fetchChecklist();
  }, [fetchChecklist]);

  // Run validation
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

  // Activate building
  const handleActivate = async () => {
    setIsActivating(true);
    setError(null);

    try {
      const result = await validationApi.activate(siteId);
      setActivationResult(result);
      setShowConfirmModal(false);

      if (result.success) {
        // Refresh checklist to get updated status
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

  // Group items by category
  const groupedItems = checklist ? groupByCategory(checklist.items) : {};

  // Loading state
  if (isLoading) {
    return (
      <Card className="p-6">
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
      </Card>
    );
  }

  // Error state
  if (error && !checklist) {
    return (
      <Card className="p-6">
        <Callout title="Error" color="rose">
          <div>{error}</div>
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={fetchChecklist}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Retry
          </Button>
        </Callout>
      </Card>
    );
  }

  if (!checklist) {
    return null;
  }

  return (
    <>
      <Card className="p-0 overflow-hidden">
        {/* Header Section */}
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
            <Button
              variant="secondary"
              size="sm"
              onClick={handleValidate}
              disabled={isValidating}
            >
              {isValidating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Validating...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Run Validation
                </>
              )}
            </Button>

            <Button
              size="sm"
              onClick={() => setShowConfirmModal(true)}
              disabled={!checklist.can_activate || isValidating}
              className={
                checklist.can_activate
                  ? "bg-green-600 hover:bg-green-700"
                  : "opacity-50 cursor-not-allowed"
              }
            >
              <Power className="w-4 h-4 mr-2" />
              Activate
            </Button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-4">
            <Callout title="Error" color="rose">
              {error}
            </Callout>
          </div>
        )}

        {/* Activation Success Alert */}
        {activationResult?.success && (
          <div className="p-4">
            <Callout title="Success" color="green">
              {activationResult.message}
            </Callout>
          </div>
        )}

        {/* Checklist Grid */}
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

                        {/* Value vs threshold */}
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

                        {/* Details */}
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

        {/* Summary Section */}
        <div
          className="p-4"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          {/* Count badges */}
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <Badge color="green" size="lg">
              {checklist.summary.passed} passed
            </Badge>
            <Badge color="red" size="lg">
              {checklist.summary.failed} failed
            </Badge>
            <Badge color="yellow" size="lg">
              {checklist.summary.warnings} warnings
            </Badge>
          </div>

          {/* Blocking issues */}
          {checklist.blocking_issues.length > 0 && (
            <div className="mb-4 p-3 rounded-md border border-red-500/50 bg-red-500/10">
              <div className="font-medium text-sm text-red-500 mb-2">Blocking Issues</div>
              <div className="space-y-1">
                {checklist.blocking_issues.map((issue, index) => (
                  <div key={index} className="text-sm text-red-400 flex items-start gap-2">
                    <span className="text-red-500 flex-shrink-0">•</span>
                    <span>{issue}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Activation status message */}
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
                <XCircle className="w-4 h-4 text-red-500" />
                Building cannot be activated until all critical issues are resolved.
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Confirmation Modal */}
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
