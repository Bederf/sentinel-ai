/**
 * Device Control & Queries API Client
 *
 * Handles device control commands, device status queries, and safety validation.
 */

import { fetchApi } from './client';

// ============= Device Types =============

export interface Device {
  id: string;
  code: string;
  name: string;
  building_id: string;
  type: string;
  status: "online" | "offline" | "error";
  health_score: number;
  points: DevicePoint[];
}

export interface DevicePoint {
  id: string;
  name: string;
  type: "analog" | "binary" | "string";
  writable: boolean;
  value: unknown;
  unit?: string;
}

export interface DeviceValue {
  point_id: string;
  value: unknown;
  timestamp: string;
}

export interface DeviceStatus {
  device_id: string;
  is_online: boolean;
  last_seen: string;
  health_score: number;
  active_alarms: number;
}

export interface DeviceControlResponse {
  success: boolean;
  message: string;
  device_id: string;
  point_id: string;
}

export interface DeviceSafetyStatus {
  device_id: string;
  status: "safe" | "warning" | "blocked";
  rules_violated: Array<{
    rule_id: string;
    name: string;
    severity: string;
  }>;
}

// ============= Device API Methods =============

export const devicesApi = {
  /**
   * Get all devices for a building
   */
  getDevices: (buildingId: string) =>
    fetchApi<Device[]>(`/api/buildings/${buildingId}/devices`),

  /**
   * Get device details
   */
  getDevice: (deviceId: string) =>
    fetchApi<Device>(`/api/devices/${deviceId}`),

  /**
   * Get device status
   */
  getStatus: (deviceId: string) =>
    fetchApi<DeviceStatus>(`/api/devices/${deviceId}/status`),

  /**
   * Query device point value
   */
  getPoint: (deviceId: string, pointId: string) =>
    fetchApi<DeviceValue>(`/api/devices/${deviceId}/points/${pointId}`),

  /**
   * Control device point
   */
  control: (deviceId: string, pointId: string, value: unknown) =>
    fetchApi<DeviceControlResponse>(`/api/devices/${deviceId}/control`, {
      method: "POST",
      body: JSON.stringify({ point_id: pointId, value }),
    }),

  /**
   * Check safety status before control
   */
  checkSafety: (deviceId: string) =>
    fetchApi<DeviceSafetyStatus>(`/api/devices/${deviceId}/safety-status`),
};

