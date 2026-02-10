/**
 * useControlAction Hook - SENTINEL control action state management
 *
 * Features:
 * - Manages control action execution state
 * - Tracks pending/success/error states
 * - Auto-clears results after configurable timeout
 * - Integrates with device control API
 *
 * Usage:
 * ```tsx
 * const { isExecuting, result, error, executeControl, clearResult } = useControlAction();
 *
 * // Execute a control action
 * await executeControl('device-001', 'setpoint_temp', 22);
 *
 * // Check state
 * if (isExecuting) { // show spinner }
 * if (result?.success) { // show success }
 * if (error) { // show error }
 * ```
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { toast } from "sonner";
import api from '@/lib/api';
import type { DeviceControlResponse } from '@/lib/api';

export interface ControlResult {
  success: boolean;
  message: string;
  deviceId: string;
  point: string;
  value: number | boolean;
  timestamp: string;
}

export interface UseControlActionOptions {
  /**
   * Timeout in milliseconds to auto-clear result/error (default: 5000)
   */
  autoClearTimeout?: number;
  /**
   * Priority level for control commands (1-16, default: 8)
   */
  defaultPriority?: number;
  /**
   * Callback when control action succeeds
   */
  onSuccess?: (result: ControlResult) => void;
  /**
   * Callback when control action fails
   */
  onError?: (error: string) => void;
}

export interface UseControlActionReturn {
  /**
   * True while a control action is being executed
   */
  isExecuting: boolean;
  /**
   * Result of the last control action (null if none or cleared)
   */
  result: ControlResult | null;
  /**
   * Error message from the last control action (null if none or cleared)
   */
  error: string | null;
  /**
   * Execute a control action on a device
   */
  executeControl: (
    deviceId: string,
    point: string,
    value: number | boolean,
    priority?: number
  ) => Promise<ControlResult | null>;
  /**
   * Manually clear the result/error state
   */
  clearResult: () => void;
  /**
   * Retry the last failed control action
   */
  retry: () => Promise<ControlResult | null>;
}

export function useControlAction(
  options: UseControlActionOptions = {}
): UseControlActionReturn {
  const {
    autoClearTimeout = 5000,
    defaultPriority = 8,
    onSuccess,
    onError,
  } = options;

  // State
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState<ControlResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Track last action for retry
  const lastActionRef = useRef<{
    deviceId: string;
    point: string;
    value: number | boolean;
    priority: number;
  } | null>(null);

  // Auto-clear timer ref
  const clearTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Clear result/error state
  const clearResult = useCallback(() => {
    setResult(null);
    setError(null);
    if (clearTimerRef.current) {
      clearTimeout(clearTimerRef.current);
      clearTimerRef.current = null;
    }
  }, []);

  // Start auto-clear timer
  const startAutoClearTimer = useCallback(() => {
    if (clearTimerRef.current) {
      clearTimeout(clearTimerRef.current);
    }
    if (autoClearTimeout > 0) {
      clearTimerRef.current = setTimeout(() => {
        clearResult();
      }, autoClearTimeout);
    }
  }, [autoClearTimeout, clearResult]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (clearTimerRef.current) {
        clearTimeout(clearTimerRef.current);
      }
    };
  }, []);

  // Execute control action
  const executeControl = useCallback(
    async (
      deviceId: string,
      point: string,
      value: number | boolean,
      priority: number = defaultPriority
    ): Promise<ControlResult | null> => {
      // Clear previous state
      setResult(null);
      setError(null);
      if (clearTimerRef.current) {
        clearTimeout(clearTimerRef.current);
        clearTimerRef.current = null;
      }

      // Store action for retry
      lastActionRef.current = { deviceId, point, value, priority };

      setIsExecuting(true);

      try {
        // Call the API
        const response: DeviceControlResponse = await api.controlDevice(
          deviceId,
          point,
          value,
          priority
        );

        // Create result object
        const controlResult: ControlResult = {
          success: response.success,
          message: response.message,
          deviceId: response.device_id,
          point: response.point,
          value: response.value,
          timestamp: new Date().toISOString(),
        };

        setResult(controlResult);
        setIsExecuting(false);

        // Format point name for display (e.g., "pump_speed" -> "Pump Speed")
        const formatPointName = (name: string) =>
          name.split("_").map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");

        const pointDisplay = formatPointName(point);

        // Format value for display
        const formatValue = (val: number | boolean) => {
          if (typeof val === "boolean") return val ? "ON" : "OFF";
          return String(val);
        };

        // Show success toast
        toast.success(`${pointDisplay} Updated`, {
          description: `Successfully set to ${formatValue(value)}`,
          duration: 3000,
        });

        // Trigger callback
        if (onSuccess) {
          onSuccess(controlResult);
        }

        // Start auto-clear timer
        startAutoClearTimer();

        return controlResult;
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Control action failed";

        setError(errorMessage);
        setIsExecuting(false);

        // Parse the error message for better user feedback
        const cleanError = errorMessage.replace("API Error: ", "").replace("Safety violation: ", "");

        // Format point name for display (e.g., "pump_speed" -> "Pump Speed")
        const formatPointName = (name: string) =>
          name.split("_").map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");

        const pointDisplay = formatPointName(point);

        // Show toast notification for safety violations
        const isSafetyViolation =
          errorMessage.toLowerCase().includes("safety") ||
          errorMessage.toLowerCase().includes("outside") ||
          errorMessage.toLowerCase().includes("limit") ||
          errorMessage.toLowerCase().includes("range");

        if (isSafetyViolation) {
          // Extract allowed range from error message if present
          const rangeMatch = cleanError.match(/\(([^)]+)\)/);
          const allowedRange = rangeMatch ? rangeMatch[1] : null;

          toast.error(`Cannot Set ${pointDisplay}`, {
            description: allowedRange
              ? `Value ${value} is outside the allowed range (${allowedRange}). Please select a value within the safe operating limits.`
              : cleanError,
            duration: 6000,
            style: {
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-red)",
              color: "var(--color-sentinel-text-primary)",
            },
          });
        } else {
          toast.error(`Failed to Set ${pointDisplay}`, {
            description: cleanError || "An unexpected error occurred. Please try again.",
            duration: 5000,
          });
        }

        // Trigger callback
        if (onError) {
          onError(errorMessage);
        }

        // Start auto-clear timer
        startAutoClearTimer();

        return null;
      }
    },
    [defaultPriority, onSuccess, onError, startAutoClearTimer]
  );

  // Retry last failed action
  const retry = useCallback(async (): Promise<ControlResult | null> => {
    if (!lastActionRef.current) {
      setError("No previous action to retry");
      startAutoClearTimer();
      return null;
    }

    const { deviceId, point, value, priority } = lastActionRef.current;
    return executeControl(deviceId, point, value, priority);
  }, [executeControl, startAutoClearTimer]);

  return {
    isExecuting,
    result,
    error,
    executeControl,
    clearResult,
    retry,
  };
}

export default useControlAction;
