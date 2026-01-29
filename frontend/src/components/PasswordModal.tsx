/**
 * PasswordModal Component - Password protection for sensitive settings
 *
 * Features:
 * - Modal dialog for entering admin password
 * - Password input with show/hide toggle
 * - Error display for incorrect password
 * - Keyboard support (Enter to submit, Escape to cancel)
 * - SENTINEL dark theme styling
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X, Lock, Eye, EyeOff, AlertCircle } from "lucide-react";

interface PasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  title?: string;
  description?: string;
}

// Admin password - in production this would be validated server-side
const ADMIN_PASSWORD = "sentinel2024";

export function PasswordModal({
  isOpen,
  onClose,
  onSuccess,
  title = "Enter Admin Password",
  description = "This section requires administrator access to modify.",
}: PasswordModalProps) {
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
    // Reset state when modal opens/closes
    if (!isOpen) {
      setPassword("");
      setError(null);
      setShowPassword(false);
    }
  }, [isOpen]);

  // Handle password submission
  const handleSubmit = useCallback(async () => {
    if (!password.trim()) {
      setError("Please enter a password");
      return;
    }

    setIsValidating(true);
    setError(null);

    // Simulate validation delay for UX
    await new Promise(resolve => setTimeout(resolve, 300));

    if (password === ADMIN_PASSWORD) {
      onSuccess();
      onClose();
    } else {
      setError("Incorrect password. Please try again.");
      setPassword("");
      inputRef.current?.focus();
    }

    setIsValidating(false);
  }, [password, onSuccess, onClose]);

  // Handle keyboard events
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Enter" && !isValidating) {
        event.preventDefault();
        handleSubmit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    },
    [handleSubmit, onClose, isValidating]
  );

  // Handle backdrop click
  const handleBackdropClick = useCallback(
    (event: React.MouseEvent) => {
      if (event.target === event.currentTarget) {
        onClose();
      }
    },
    [onClose]
  );

  if (!isOpen) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0, 0, 0, 0.75)" }}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="password-modal-title"
    >
      <div
        className="w-full max-w-md rounded-lg overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
        }}
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between p-4"
          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(220, 38, 38, 0.15)",
                color: "var(--color-sentinel-red)",
              }}
            >
              <Lock className="h-5 w-5" />
            </div>
            <h2
              id="password-modal-title"
              className="text-base font-medium"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              {title}
            </h2>
          </div>
          <button
            onClick={onClose}
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
          <p
            className="text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {description}
          </p>

          {/* Error message */}
          {error && (
            <div
              className="flex items-center gap-2 p-3 rounded"
              style={{
                background: "rgba(220, 38, 38, 0.15)",
                border: "1px solid rgba(220, 38, 38, 0.3)",
              }}
            >
              <AlertCircle
                className="h-4 w-4 flex-shrink-0"
                style={{ color: "var(--color-sentinel-red)" }}
              />
              <span
                className="text-sm"
                style={{ color: "var(--color-sentinel-red)" }}
              >
                {error}
              </span>
            </div>
          )}

          {/* Password input */}
          <div>
            <label
              className="block text-sm font-medium mb-2"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Password
            </label>
            <div className="relative">
              <input
                ref={inputRef}
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter admin password"
                disabled={isValidating}
                className="w-full px-3 py-2 pr-10 rounded text-sm"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: `1px solid ${error ? "var(--color-sentinel-red)" : "var(--color-sentinel-border)"}`,
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:brightness-110 transition-colors"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
                tabIndex={-1}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-end gap-3 p-4"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          <button
            onClick={onClose}
            disabled={isValidating}
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
            onClick={handleSubmit}
            disabled={isValidating || !password.trim()}
            className="px-4 py-2 rounded text-sm font-medium transition-colors hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: "var(--color-sentinel-red)",
              color: "#ffffff",
            }}
          >
            {isValidating ? "Verifying..." : "Unlock"}
          </button>
        </div>

        {/* Keyboard hint */}
        <div
          className="px-4 pb-3 text-center"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        >
          <span className="text-xs">
            Press <kbd className="px-1 py-0.5 rounded bg-black/20">Enter</kbd> to
            submit or <kbd className="px-1 py-0.5 rounded bg-black/20">Esc</kbd>{" "}
            to cancel
          </span>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default PasswordModal;
