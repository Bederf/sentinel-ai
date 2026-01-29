/**
 * ControlConfirmModal Component - SENTINEL control action confirmation
 *
 * Features:
 * - Confirmation dialog before executing control actions
 * - Shows device name, point, current and new values
 * - Safety status badge with warnings
 * - Keyboard support (Escape to cancel, Enter to confirm)
 * - Grafana-style dark theme
 *
 * Follows SENTINEL dark theme design system.
 */

import { useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import {
  X,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Shield,
  ArrowRight,
} from "lucide-react";

interface SafetyStatus {
  status: "safe" | "warning" | "blocked";
  message?: string;
}

interface ControlConfirmModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Called when user confirms the action */
  onConfirm: () => void;
  /** Called when user cancels */
  onCancel: () => void;
  /** Device name */
  deviceName: string;
  /** Point name being changed */
  point: string;
  /** Point description (human-readable label) */
  pointDescription?: string;
  /** Current value before change */
  currentValue: number | boolean;
  /** New value to be set */
  newValue: number | boolean;
  /** Unit for the value (e.g., "C", "%") */
  unit?: string;
  /** Safety status for the action */
  safetyStatus?: SafetyStatus;
  /** Whether the confirm action is disabled (e.g., while loading) */
  confirmDisabled?: boolean;
}

/**
 * Format value for display
 */
function formatValue(value: number | boolean, unit?: string): string {
  if (typeof value === "boolean") {
    return value ? "ON" : "OFF";
  }
  if (unit) {
    return `${value}${unit}`;
  }
  return String(value);
}

/**
 * Get safety status configuration
 */
function getSafetyConfig(status: string): {
  color: string;
  bg: string;
  icon: React.ReactNode;
  label: string;
} {
  switch (status) {
    case "safe":
      return {
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        icon: <CheckCircle className="h-4 w-4" />,
        label: "Safe",
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        icon: <AlertTriangle className="h-4 w-4" />,
        label: "Warning",
      };
    case "blocked":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        icon: <XCircle className="h-4 w-4" />,
        label: "Blocked",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        icon: <Shield className="h-4 w-4" />,
        label: "Unknown",
      };
  }
}

export function ControlConfirmModal({
  isOpen,
  onConfirm,
  onCancel,
  deviceName,
  point,
  pointDescription,
  currentValue,
  newValue,
  unit,
  safetyStatus = { status: "safe" },
  confirmDisabled = false,
}: ControlConfirmModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  const safetyConfig = getSafetyConfig(safetyStatus.status);
  const isBlocked = safetyStatus.status === "blocked";

  // Handle keyboard events
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen) return;

      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      } else if (event.key === "Enter" && !confirmDisabled && !isBlocked) {
        event.preventDefault();
        onConfirm();
      }
    },
    [isOpen, onCancel, onConfirm, confirmDisabled, isBlocked]
  );

  // Add keyboard listener
  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);

  // Focus confirm button when modal opens
  useEffect(() => {
    if (isOpen && confirmButtonRef.current) {
      confirmButtonRef.current.focus();
    }
  }, [isOpen]);

  // Handle backdrop click
  const handleBackdropClick = useCallback(
    (event: React.MouseEvent) => {
      if (event.target === event.currentTarget) {
        onCancel();
      }
    },
    [onCancel]
  );

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0, 0, 0, 0.75)" }}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
    >
      <div
        ref={modalRef}
        className="w-full max-w-md rounded-lg overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between p-4"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <h2
            id="confirm-modal-title"
            className="text-base font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Confirm Control Action
          </h2>
          <button
            onClick={onCancel}
            className="p-1 rounded hover:brightness-110 transition-colors"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-secondary)",
            }}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {/* Device info */}
          <div
            className="p-3 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="text-xs uppercase tracking-wider mb-1"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Device
            </div>
            <div
              className="font-medium"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {deviceName}
            </div>
          </div>

          {/* Point info */}
          <div
            className="p-3 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="text-xs uppercase tracking-wider mb-1"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Point
            </div>
            <div
              className="font-medium"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {pointDescription || point}
            </div>
            {pointDescription && (
              <div
                className="text-xs mt-0.5"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {point}
              </div>
            )}
          </div>

          {/* Value change */}
          <div
            className="p-3 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div
              className="text-xs uppercase tracking-wider mb-2"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              Change
            </div>
            <div className="flex items-center justify-center gap-3">
              <div className="text-center">
                <div
                  className="text-xs mb-1"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Current
                </div>
                <div
                  className="text-xl font-mono font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {formatValue(currentValue, unit)}
                </div>
              </div>
              <ArrowRight
                className="h-5 w-5"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              />
              <div className="text-center">
                <div
                  className="text-xs mb-1"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  New
                </div>
                <div
                  className="text-xl font-mono font-semibold"
                  style={{ color: "var(--color-sentinel-blue)" }}
                >
                  {formatValue(newValue, unit)}
                </div>
              </div>
            </div>
          </div>

          {/* Safety status */}
          <div
            className="p-3 rounded flex items-start gap-2"
            style={{
              background: safetyConfig.bg,
              border: `1px solid ${safetyConfig.color}30`,
            }}
          >
            <div style={{ color: safetyConfig.color }}>{safetyConfig.icon}</div>
            <div className="flex-1">
              <div
                className="text-sm font-medium"
                style={{ color: safetyConfig.color }}
              >
                Safety: {safetyConfig.label}
              </div>
              {safetyStatus.message && (
                <div
                  className="text-xs mt-0.5"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {safetyStatus.message}
                </div>
              )}
            </div>
          </div>

          {/* Blocked warning */}
          {isBlocked && (
            <div
              className="p-3 rounded"
              style={{
                background: "rgba(220, 38, 38, 0.1)",
                border: "1px solid var(--color-sentinel-red)",
              }}
            >
              <div
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-red)" }}
              >
                This action is blocked by safety rules.
              </div>
              <div
                className="text-xs mt-1"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Contact a supervisor to override or adjust safety parameters.
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-end gap-3 p-4"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            Cancel
          </button>
          <button
            ref={confirmButtonRef}
            onClick={onConfirm}
            disabled={confirmDisabled || isBlocked}
            className="px-4 py-2 rounded text-sm font-medium transition-colors hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: isBlocked
                ? "var(--color-sentinel-bg-secondary)"
                : "var(--color-sentinel-blue)",
              color: isBlocked
                ? "var(--color-sentinel-text-disabled)"
                : "#ffffff",
            }}
          >
            {isBlocked ? "Blocked" : "Confirm"}
          </button>
        </div>

        {/* Keyboard hint */}
        <div
          className="px-4 pb-3 text-center"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          <span className="text-xs">
            Press <kbd className="px-1 py-0.5 rounded bg-black/20">Enter</kbd>{" "}
            to confirm or{" "}
            <kbd className="px-1 py-0.5 rounded bg-black/20">Esc</kbd> to cancel
          </span>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default ControlConfirmModal;
