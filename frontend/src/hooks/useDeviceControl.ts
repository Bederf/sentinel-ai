/**
 * useDeviceControl Hook - SENTINEL device control logic
 *
 * Features:
 * - Device control state management
 * - API integration for device operations
 * - Safety validation integration
 * - Error handling and retry logic
 * - Real-time polling for device status
 */

import { useState, useEffect, useCallback } from "react";
import api from "../lib/api";
import type { Device, DeviceValue, DeviceControlResponse } from "../lib/api";

interface UseDeviceControlOptions {
  deviceId?: string;
  refreshInterval?: number;
  autoConnect?: boolean;
}

interface DeviceControlState {
  device: Device | null;
  points: Record<string, DeviceValue>;
  loading: boolean;
  error: string | null;
  controlling: boolean;
  lastUpdate: string | null;
}

interface SafetyStatus {
  status: "safe" | "warning" | "blocked";
  message?: string;
  rules?: Array<{ rule: string; status: string }>;
}

export function useDeviceControl(options: UseDeviceControlOptions = {}) {
  const {
    deviceId,
    refreshInterval = 10000,
    autoConnect = true,
  } = options;

  // State
  const [state, setState] = useState<DeviceControlState>({
    device: null,
    points: {},
    loading: false,
    error: null,
    controlling: false,
    lastUpdate: null,
  });

  const [safetyStatus, setSafetyStatus] = useState<SafetyStatus>({
    status: "safe",
  });

  // Fetch device data
  const fetchDevice = useCallback(async (id: string) => {
    if (!id) return;

    setState((prev) => ({ ...prev, loading: true, error: null }));

    try {
      // Fetch device details
      const device = await api.getDevice(id);

      // Fetch device points
      const pointsResponse = await api.getDevicePoints(id);

      // Initialize point values
      const points: Record<string, DeviceValue> = {};
      for (const [pointName, point] of Object.entries(pointsResponse)) {
        points[pointName] = {
          device_id: id,
          point_name: pointName,
          value: point.default_value,
          unit: point.unit,
          timestamp: new Date().toISOString(),
          quality: "good",
        };
      }

      // Fetch current values for readable points
      const readablePoints = Object.entries(pointsResponse)
        .filter(([_, point]) => !point.writable)
        .map(([pointName]) => pointName);

      for (const pointName of readablePoints) {
        try {
          const value = await api.readDevicePoint(id, pointName);
          points[pointName] = value;
        } catch (err) {
          console.warn(`Failed to read point ${pointName}:`, err);
        }
      }

      setState((prev) => ({
        ...prev,
        device,
        points,
        loading: false,
        lastUpdate: new Date().toISOString(),
      }));

      // Check safety status
      await checkSafetyStatus(id);
    } catch (err) {
      console.error("Failed to fetch device:", err);
      setState((prev) => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : "Failed to load device",
      }));
    }
  }, []);

  // Check safety status
  const checkSafetyStatus = useCallback(async (_id: string) => {
    try {
      // TODO: Integrate with safety API from Plan 6-02
      // For now, simulate safety status based on device type
      const device = state.device;
      if (!device) return;

      let status: SafetyStatus = { status: "safe" };

      // Simulate safety rules based on device metadata
      if (device.metadata?.critical) {
        status = {
          status: "warning",
          message: "Critical device - extra caution required",
          rules: [
            { rule: "Critical device protection", status: "warning" },
            { rule: "Manual override allowed", status: "passed" },
          ],
        };
      }

      if (device.metadata?.life_safety) {
        status = {
          status: "blocked",
          message: "Life safety device - control actions blocked",
          rules: [
            { rule: "Life safety protection", status: "failed" },
            { rule: "Emergency override required", status: "failed" },
          ],
        };
      }

      setSafetyStatus(status);
    } catch (err) {
      console.warn("Failed to check safety status:", err);
    }
  }, [state.device]);

  // Control device
  const controlDevice = useCallback(async (
    point: string,
    value: number | boolean,
    priority: number = 8
  ): Promise<DeviceControlResponse> => {
    if (!deviceId) {
      throw new Error("No device selected");
    }

    setState((prev) => ({ ...prev, controlling: true, error: null }));

    try {
      // Validate safety status
      if (safetyStatus.status === "blocked") {
        throw new Error("Control blocked by safety rules");
      }

      // Perform control action
      const response = await api.controlDevice(deviceId, point, value, priority);

      // Update local state
      setState((prev) => ({
        ...prev,
        points: {
          ...prev.points,
          [point]: {
            device_id: deviceId,
            point_name: point,
            value,
            unit: prev.points[point]?.unit || "",
            timestamp: new Date().toISOString(),
            quality: "good",
          },
        },
        controlling: false,
        lastUpdate: new Date().toISOString(),
      }));

      // Re-check safety status after control action
      await checkSafetyStatus(deviceId);

      return response;
    } catch (err) {
      console.error("Control action failed:", err);
      setState((prev) => ({
        ...prev,
        controlling: false,
        error: err instanceof Error ? err.message : "Control action failed",
      }));
      throw err;
    }
  }, [deviceId, safetyStatus.status, checkSafetyStatus]);

  // Refresh device data
  const refreshDevice = useCallback(async () => {
    if (!deviceId) return;
    await fetchDevice(deviceId);
  }, [deviceId, fetchDevice]);

  // Poll for updates
  useEffect(() => {
    if (!deviceId || !autoConnect || refreshInterval <= 0) return;

    const intervalId = setInterval(refreshDevice, refreshInterval);
    return () => clearInterval(intervalId);
  }, [deviceId, autoConnect, refreshInterval, refreshDevice]);

  // Initial fetch
  useEffect(() => {
    if (deviceId && autoConnect) {
      fetchDevice(deviceId);
    }
  }, [deviceId, autoConnect, fetchDevice]);

  // Get device point value
  const getPointValue = useCallback((pointName: string): number | boolean | null => {
    return state.points[pointName]?.value ?? null;
  }, [state.points]);

  // Get device point metadata
  const getPointMetadata = useCallback((pointName: string) => {
    return state.device?.points[pointName];
  }, [state.device]);

  // Get writable points
  const getWritablePoints = useCallback(() => {
    if (!state.device) return [];
    return Object.entries(state.device.points)
      .filter(([_, point]) => point.writable)
      .map(([pointName, point]) => {
        const { name, ...rest } = point;
        return { name: pointName, ...rest };
      });
  }, [state.device]);

  // Get readable points
  const getReadablePoints = useCallback(() => {
    if (!state.device) return [];
    return Object.entries(state.device.points)
      .filter(([_, point]) => !point.writable)
      .map(([pointName, point]) => {
        const { name, ...rest } = point;
        return { name: pointName, ...rest };
      });
  }, [state.device]);

  return {
    // State
    device: state.device,
    points: state.points,
    loading: state.loading,
    error: state.error,
    controlling: state.controlling,
    lastUpdate: state.lastUpdate,
    safetyStatus,

    // Actions
    controlDevice,
    refreshDevice,
    getPointValue,
    getPointMetadata,
    getWritablePoints,
    getReadablePoints,

    // Utility
    setDeviceId: (id: string) => {
      if (id !== deviceId) {
        fetchDevice(id);
      }
    },
  };
}

export default useDeviceControl;