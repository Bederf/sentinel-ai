/**
 * Devices API Tests (devices.ts)
 *
 * Tests comprehensive device API functionality:
 * - Device queries (getDevices, getDevice, getStatus)
 * - Device control (control method with validation)
 * - Safety checks (checkSafety, getSafetyStatus)
 * - Error handling
 * - Request payload validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { devicesApi } from '../devices';
import type { Device, DeviceStatus, DeviceSafetyStatus, DeviceControlResponse } from '../devices';

// Mock the fetchApi function
vi.mock('../client', () => ({
  fetchApi: vi.fn(),
}));

import { fetchApi } from '../client';

const mockDevice: Device = {
  id: 'device-001',
  code: 'S002-CHILLER-B1-001',
  name: 'Chiller Unit 1',
  site_id: 'building-001',
  type: 'CHILLER',
  status: 'online',
  health_score: 85,
  points: [
    {
      id: 'point-001',
      name: 'Supply Temperature',
      type: 'analog',
      writable: false,
      value: 6.5,
      unit: '°C',
    },
    {
      id: 'point-002',
      name: 'Setpoint',
      type: 'analog',
      writable: true,
      value: 7.0,
      unit: '°C',
    },
  ],
};

const mockDeviceStatus: DeviceStatus = {
  device_id: 'device-001',
  is_online: true,
  last_seen: new Date().toISOString(),
  health_score: 85,
  active_alarms: 0,
};

const mockSafetyStatus: DeviceSafetyStatus = {
  device_id: 'device-001',
  status: 'safe',
  rules_violated: [],
};

describe('DevicesApi - Device Queries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getDevices', () => {
    it('should fetch devices for a building', async () => {
      const mockDevices = [mockDevice];
      (fetchApi as any).mockResolvedValueOnce(mockDevices);

      const result = await devicesApi.getDevices('building-001');

      expect(result).toEqual(mockDevices);
      expect(fetchApi).toHaveBeenCalledWith('/api/buildings/building-001/devices');
    });

    it('should call correct endpoint with building ID', async () => {
      (fetchApi as any).mockResolvedValueOnce([]);

      await devicesApi.getDevices('building-002');

      expect(fetchApi).toHaveBeenCalledWith('/api/buildings/building-002/devices');
    });

    it('should handle empty device list', async () => {
      (fetchApi as any).mockResolvedValueOnce([]);

      const result = await devicesApi.getDevices('building-001');

      expect(result).toEqual([]);
    });

    it('should handle multiple devices', async () => {
      const mockDevices = [
        mockDevice,
        { ...mockDevice, id: 'device-002', code: 'S002-AHU-L2-001', type: 'AHU' },
        { ...mockDevice, id: 'device-003', code: 'S002-FCU-L1-A', type: 'FCU' },
      ];
      (fetchApi as any).mockResolvedValueOnce(mockDevices);

      const result = await devicesApi.getDevices('building-001');

      expect(result).toHaveLength(3);
      expect(result[0].type).toBe('CHILLER');
      expect(result[1].type).toBe('AHU');
      expect(result[2].type).toBe('FCU');
    });
  });

  describe('getDevice', () => {
    it('should fetch single device by ID', async () => {
      (fetchApi as any).mockResolvedValueOnce(mockDevice);

      const result = await devicesApi.getDevice('device-001');

      expect(result).toEqual(mockDevice);
      expect(fetchApi).toHaveBeenCalledWith('/api/devices/device-001');
    });

    it('should include device points', async () => {
      (fetchApi as any).mockResolvedValueOnce(mockDevice);

      const result = await devicesApi.getDevice('device-001');

      expect(result.points).toHaveLength(2);
      expect(result.points[0].name).toBe('Supply Temperature');
      expect(result.points[0].writable).toBe(false);
      expect(result.points[1].writable).toBe(true);
    });

    it('should validate device structure', async () => {
      (fetchApi as any).mockResolvedValueOnce(mockDevice);

      const result = await devicesApi.getDevice('device-001');

      expect(result.id).toBeDefined();
      expect(result.code).toBeDefined();
      expect(result.name).toBeDefined();
      expect(result.site_id).toBeDefined();
      expect(result.type).toBeDefined();
      expect(result.status).toBeDefined();
      expect(result.health_score).toBeDefined();
    });
  });

  describe('getStatus', () => {
    it('should fetch device status', async () => {
      (fetchApi as any).mockResolvedValueOnce(mockDeviceStatus);

      const result = await devicesApi.getStatus('device-001');

      expect(result).toEqual(mockDeviceStatus);
      expect(fetchApi).toHaveBeenCalledWith('/api/devices/device-001/status');
    });

    it('should include online status', async () => {
      (fetchApi as any).mockResolvedValueOnce(mockDeviceStatus);

      const result = await devicesApi.getStatus('device-001');

      expect(result.is_online).toBe(true);
    });

    it('should include health score', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        ...mockDeviceStatus,
        health_score: 65,
      });

      const result = await devicesApi.getStatus('device-001');

      expect(result.health_score).toBe(65);
    });

    it('should include active alarms count', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        ...mockDeviceStatus,
        active_alarms: 2,
      });

      const result = await devicesApi.getStatus('device-001');

      expect(result.active_alarms).toBe(2);
    });

    it('should handle offline device', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        ...mockDeviceStatus,
        is_online: false,
        active_alarms: 5,
      });

      const result = await devicesApi.getStatus('device-001');

      expect(result.is_online).toBe(false);
      expect(result.active_alarms).toBe(5);
    });
  });
});

describe('DevicesApi - Device Control', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('control', () => {
    it('should control device point with value', async () => {
      const mockResponse: DeviceControlResponse = {
        success: true,
        message: 'Control command executed',
        device_id: 'device-001',
        point_id: 'point-002',
      };
      (fetchApi as any).mockResolvedValueOnce(mockResponse);

      const result = await devicesApi.control('device-001', 'point-002', 8.0);

      expect(result.success).toBe(true);
      expect(result.message).toContain('Control');
    });

    it('should send correct request body', async () => {
      (fetchApi as any).mockResolvedValueOnce({ success: true });

      await devicesApi.control('device-001', 'point-002', 8.5);

      expect(fetchApi).toHaveBeenCalledWith(
        '/api/devices/device-001/control',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            point_id: 'point-002',
            value: 8.5,
          }),
        })
      );
    });

    it('should handle numeric values', async () => {
      (fetchApi as any).mockResolvedValueOnce({ success: true });

      await devicesApi.control('device-001', 'point-002', 7.5);

      expect(fetchApi).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('7.5'),
        })
      );
    });

    it('should handle boolean values', async () => {
      (fetchApi as any).mockResolvedValueOnce({ success: true });

      await devicesApi.control('device-001', 'point-003', true);

      expect(fetchApi).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('true'),
        })
      );
    });

    it('should handle string values', async () => {
      (fetchApi as any).mockResolvedValueOnce({ success: true });

      await devicesApi.control('device-001', 'point-004', 'ON');

      expect(fetchApi).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('ON'),
        })
      );
    });

    it('should return control response with metadata', async () => {
      const mockResponse: DeviceControlResponse = {
        success: true,
        message: 'Setpoint updated',
        device_id: 'device-001',
        point_id: 'point-002',
      };
      (fetchApi as any).mockResolvedValueOnce(mockResponse);

      const result = await devicesApi.control('device-001', 'point-002', 8.0);

      expect(result.device_id).toBe('device-001');
      expect(result.point_id).toBe('point-002');
    });

    it('should validate endpoint URL construction', async () => {
      (fetchApi as any).mockResolvedValueOnce({ success: true });

      await devicesApi.control('dev-xyz', 'point-abc', 100);

      expect(fetchApi).toHaveBeenCalledWith(
        '/api/devices/dev-xyz/control',
        expect.any(Object)
      );
    });
  });
});

describe('DevicesApi - Safety Checks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('checkSafety', () => {
    it('should fetch device safety status', async () => {
      (fetchApi as any).mockResolvedValueOnce(mockSafetyStatus);

      const result = await devicesApi.checkSafety('device-001');

      expect(result).toEqual(mockSafetyStatus);
      expect(fetchApi).toHaveBeenCalledWith('/api/devices/device-001/safety-status');
    });

    it('should indicate safe status', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        device_id: 'device-001',
        status: 'safe',
        rules_violated: [],
      });

      const result = await devicesApi.checkSafety('device-001');

      expect(result.status).toBe('safe');
      expect(result.rules_violated).toHaveLength(0);
    });

    it('should indicate warning status with violations', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        device_id: 'device-001',
        status: 'warning',
        rules_violated: [
          {
            rule_id: 'rule-001',
            name: 'Temperature Limit',
            severity: 'warning',
          },
        ],
      });

      const result = await devicesApi.checkSafety('device-001');

      expect(result.status).toBe('warning');
      expect(result.rules_violated).toHaveLength(1);
      expect(result.rules_violated[0].name).toBe('Temperature Limit');
    });

    it('should indicate blocked status on critical violations', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        device_id: 'device-001',
        status: 'blocked',
        rules_violated: [
          {
            rule_id: 'rule-002',
            name: 'Pressure Override',
            severity: 'critical',
          },
          {
            rule_id: 'rule-003',
            name: 'Temperature Override',
            severity: 'critical',
          },
        ],
      });

      const result = await devicesApi.checkSafety('device-001');

      expect(result.status).toBe('blocked');
      expect(result.rules_violated).toHaveLength(2);
    });

    it('should handle multiple rule violations', async () => {
      (fetchApi as any).mockResolvedValueOnce({
        device_id: 'device-001',
        status: 'warning',
        rules_violated: [
          { rule_id: 'r1', name: 'Rule 1', severity: 'warning' },
          { rule_id: 'r2', name: 'Rule 2', severity: 'warning' },
          { rule_id: 'r3', name: 'Rule 3', severity: 'warning' },
        ],
      });

      const result = await devicesApi.checkSafety('device-001');

      expect(result.rules_violated).toHaveLength(3);
    });

    it('should validate safety status enum values', async () => {
      const statuses = ['safe', 'warning', 'blocked'];

      for (const status of statuses) {
        (fetchApi as any).mockResolvedValueOnce({
          device_id: 'device-001',
          status,
          rules_violated: [],
        });

        const result = await devicesApi.checkSafety('device-001');
        expect(['safe', 'warning', 'blocked']).toContain(result.status);
      }
    });
  });
});

describe('DevicesApi - getPoint', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch device point value', async () => {
    const mockPointValue = {
      point_id: 'point-001',
      value: 6.5,
      timestamp: new Date().toISOString(),
    };
    (fetchApi as any).mockResolvedValueOnce(mockPointValue);

    const result = await devicesApi.getPoint('device-001', 'point-001');

    expect(result).toEqual(mockPointValue);
    expect(fetchApi).toHaveBeenCalledWith(
      '/api/devices/device-001/points/point-001'
    );
  });

  it('should construct correct endpoint URL', async () => {
    (fetchApi as any).mockResolvedValueOnce({ value: 0 });

    await devicesApi.getPoint('dev-xyz', 'point-123');

    expect(fetchApi).toHaveBeenCalledWith(
      '/api/devices/dev-xyz/points/point-123'
    );
  });

  it('should include timestamp in response', async () => {
    const timestamp = new Date().toISOString();
    (fetchApi as any).mockResolvedValueOnce({
      point_id: 'point-001',
      value: 25.3,
      timestamp,
    });

    const result = await devicesApi.getPoint('device-001', 'point-001');

    expect(result.timestamp).toBe(timestamp);
  });
});

describe('DevicesApi - Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should propagate fetchApi errors', async () => {
    const error = new Error('Network error');
    (fetchApi as any).mockRejectedValueOnce(error);

    await expect(devicesApi.getDevices('building-001')).rejects.toThrow(
      'Network error'
    );
  });

  it('should handle 404 device not found', async () => {
    const error = new Error('Device not found');
    (fetchApi as any).mockRejectedValueOnce(error);

    await expect(devicesApi.getDevice('nonexistent')).rejects.toThrow(
      'Device not found'
    );
  });

  it('should handle 403 permission denied on control', async () => {
    const error = new Error('Permission denied');
    (fetchApi as any).mockRejectedValueOnce(error);

    await expect(devicesApi.control('device-001', 'point-002', 8.0)).rejects.toThrow(
      'Permission denied'
    );
  });

  it('should handle 429 rate limit errors', async () => {
    const error = new Error('Rate limited');
    (fetchApi as any).mockRejectedValueOnce(error);

    await expect(devicesApi.getStatus('device-001')).rejects.toThrow(
      'Rate limited'
    );
  });
});
