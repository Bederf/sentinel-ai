/**
 * Control Dashboard Component - Building Management Control Center
 *
 * Features:
 * - Two-column layout: Device list (left), Control panel (right)
 * - Real-time device status updates
 * - Safety validation indicators
 * - Audit logging integration (now in separate tab)
 * - Grafana-style design consistency
 *
 * Integration with:
 * - Device abstraction service (backend)
 * - Safety interlock validation
 * - Audit logger (via ControlAuditTrail component)
 * - Existing dashboard theme
 */

import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  Activity,
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
} from "lucide-react";
import api from "../lib/api";
import type { Device } from "../lib/api";
import { DeviceList } from "./DeviceList";
import { ControlPanel } from "./ControlPanel";
import { LoadingCard } from "./LoadingCard";

interface ControlDashboardProps {
  onError?: (error: string) => void;
}

export function ControlDashboard({ onError }: ControlDashboardProps) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshDevices, setRefreshDevices] = useState(0);

  // Load devices on mount
  useEffect(() => {
    const loadDevices = async () => {
      try {
        setIsLoading(true);
        const devices = await api.getDevices();
        setDevices(devices);
        // Auto-select first device if none selected
        if (devices.length > 0 && !selectedDevice) {
          setSelectedDevice(devices[0]);
        }
      } catch (error) {
        console.error("Failed to load devices:", error);
        onError?.("Failed to load control devices");
      } finally {
        setIsLoading(false);
      }
    };

    loadDevices();
  }, [refreshDevices]);

  const handleDeviceSelect = useCallback(async (device: Device) => {
    try {
      setSelectedDevice(device);
      // Optionally refresh device data when selected
      const refreshedDevice = await api.getDevice(device.id);
      setSelectedDevice(refreshedDevice);
    } catch (error) {
      console.error("Failed to refresh device:", error);
      // Keep the device selected even if refresh fails
    }
  }, []);

  const handleControlAction = useCallback(async (deviceId: string, point: string, value: number | boolean) => {
    try {
      await api.controlDevice(deviceId, point, value);
      // Refresh devices after successful control
      setRefreshDevices((prev) => prev + 1);
    } catch (error) {
      console.error("Control action failed:", error);
      throw error;
    }
  }, []);

  if (isLoading) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <LoadingCard />
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-hidden flex"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Left Column: Device List */}
      <div className="w-80 flex flex-col border-r" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div
          className="flex-none p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Cpu className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Control Devices
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {devices.filter((d) => d.status === "online").length} online, {devices.filter((d) => d.status === "offline").length} offline
              </span>
            </div>
          </div>
          <button
            onClick={() => setRefreshDevices((prev) => prev + 1)}
            className="p-1 rounded transition-colors"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            title="Refresh devices"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <DeviceList
            devices={devices}
            selectedDevice={selectedDevice}
            onDeviceSelect={handleDeviceSelect}
          />
        </div>
      </div>

      {/* Center Column: Control Panel */}
      <div className="flex-1 flex flex-col">
        <div
          className="flex-none p-4 border-b flex items-center justify-between"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(245, 158, 11, 0.15)" }}
            >
              <Activity className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
            </div>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Control Panel
              </h3>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {selectedDevice ? selectedDevice.name : "Select a device"}
              </span>
            </div>
          </div>
          {selectedDevice && (
            <div className="flex items-center gap-2">
              <div
                className={`px-2 py-1 rounded text-xs font-medium ${
                  (selectedDevice.safety_status || "unknown") === "safe"
                    ? "bg-green-500/10 text-green-500"
                    : (selectedDevice.safety_status || "unknown") === "warning"
                    ? "bg-yellow-500/10 text-yellow-500"
                    : "bg-red-500/10 text-red-500"
                }`}
              >
                {(selectedDevice.safety_status || "unknown") === "safe" ? (
                  <CheckCircle className="h-3 w-3 inline mr-1" />
                ) : (selectedDevice.safety_status || "unknown") === "warning" ? (
                  <AlertTriangle className="h-3 w-3 inline mr-1" />
                ) : (
                  <XCircle className="h-3 w-3 inline mr-1" />
                )}
                {(selectedDevice.safety_status || "unknown").toUpperCase()}
              </div>
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          <ControlPanel
            device={selectedDevice}
            onControl={handleControlAction}
            safetyStatus={{
              status: selectedDevice.safety_status || "safe",
            }}
          />
        </div>
      </div>
    </div>
  );
}