/* eslint-disable react-hooks/set-state-in-effect */
/**
 * ControlFeedback Component - SENTINEL control action feedback display
 *
 * Features:
 * - Shows pending/success/error states with appropriate icons
 * - Animated state transitions
 * - Retry button on error
 * - Auto-fade success messages
 * - Grafana-style dark theme
 *
 * Follows SENTINEL dark theme design system.
 */

import { useEffect, useState } from "react";
import { RefreshCw, CheckCircle, XCircle, RotateCcw } from "lucide-react";
import type { ControlResult } from "../hooks/useControlAction";

export type FeedbackState = "idle" | "pending" | "success" | "error";

interface ControlFeedbackProps {
  /** Current feedback state */
  state: FeedbackState;
  /** Result from successful control action */
  result?: ControlResult | null;
  /** Error message for failed action */
  error?: string | null;
  /** Called when user clicks retry */
  onRetry?: () => void;
  /** Called when user dismisses the feedback */
  onDismiss?: () => void;
  /** Compact mode for inline display */
  compact?: boolean;
}

export function ControlFeedback({
  state,
  result,
  error,
  onRetry,
  onDismiss,
  compact = false,
}: ControlFeedbackProps) {
  const [visible, setVisible] = useState(false);
  const [fadeOut, setFadeOut] = useState(false);

  // Handle visibility and fade animations
  useEffect(() => {
    if (state === "idle") {
      setFadeOut(true);
      const timer = setTimeout(() => {
        setVisible(false);
        setFadeOut(false);
      }, 300);
      return () => clearTimeout(timer);
    } else {
      setVisible(true);
      setFadeOut(false);
    }
  }, [state]);

  // Auto-fade success after a brief moment (visual only, timer is managed by hook)
  useEffect(() => {
    if (state === "success") {
      const timer = setTimeout(() => {
        setFadeOut(true);
      }, 4000); // Start fade 1 second before auto-clear
      return () => clearTimeout(timer);
    }
  }, [state]);

  if (!visible) return null;

  // Render pending state
  if (state === "pending") {
    return (
      <div
        className={`flex items-center gap-2 ${
          compact ? "py-1" : "p-3 rounded"
        } transition-opacity duration-300 ${fadeOut ? "opacity-0" : "opacity-100"}`}
        style={
          compact
            ? {}
            : {
                background: "rgba(59, 130, 246, 0.15)",
                border: "1px solid rgba(59, 130, 246, 0.3)",
              }
        }
        role="status"
        aria-live="polite"
      >
        <RefreshCw
          className="h-4 w-4 animate-spin flex-shrink-0"
          style={{ color: "var(--color-sentinel-blue)" }}
        />
        <span
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Executing control action...
        </span>
      </div>
    );
  }

  // Render success state
  if (state === "success" && result) {
    return (
      <div
        className={`flex items-center gap-2 ${
          compact ? "py-1" : "p-3 rounded"
        } transition-opacity duration-300 ${fadeOut ? "opacity-0" : "opacity-100"}`}
        style={
          compact
            ? {}
            : {
                background: "rgba(16, 185, 129, 0.15)",
                border: "1px solid rgba(16, 185, 129, 0.3)",
              }
        }
        role="status"
        aria-live="polite"
      >
        <CheckCircle
          className="h-4 w-4 flex-shrink-0"
          style={{ color: "var(--color-sentinel-green)" }}
        />
        <div className="flex-1 min-w-0">
          <span
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-green)" }}
          >
            Control applied
          </span>
          {!compact && (
            <span
              className="text-sm ml-2"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {result.point} set to {String(result.value)}
            </span>
          )}
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="p-1 rounded hover:brightness-110 transition-colors flex-shrink-0"
            style={{
              background: "transparent",
              color: "var(--color-sentinel-text-disabled)",
            }}
            aria-label="Dismiss"
          >
            <XCircle className="h-3 w-3" />
          </button>
        )}
      </div>
    );
  }

  // Render error state
  if (state === "error" && error) {
    return (
      <div
        className={`flex items-center gap-2 ${
          compact ? "py-1" : "p-3 rounded"
        } transition-opacity duration-300 ${fadeOut ? "opacity-0" : "opacity-100"}`}
        style={
          compact
            ? {}
            : {
                background: "rgba(220, 38, 38, 0.15)",
                border: "1px solid rgba(220, 38, 38, 0.3)",
              }
        }
        role="alert"
        aria-live="assertive"
      >
        <XCircle
          className="h-4 w-4 flex-shrink-0"
          style={{ color: "var(--color-sentinel-red)" }}
        />
        <div className="flex-1 min-w-0">
          <span
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-red)" }}
          >
            Control failed
          </span>
          {!compact && (
            <p
              className="text-xs mt-0.5 truncate"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
              title={error}
            >
              {error}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {onRetry && (
            <button
              onClick={onRetry}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{
                background: "rgba(220, 38, 38, 0.2)",
                color: "var(--color-sentinel-red)",
              }}
            >
              <RotateCcw className="h-3 w-3" />
              Retry
            </button>
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="p-1 rounded hover:brightness-110 transition-colors"
              style={{
                background: "transparent",
                color: "var(--color-sentinel-text-disabled)",
              }}
              aria-label="Dismiss"
            >
              <XCircle className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
    );
  }

  return null;
}

export default ControlFeedback;
