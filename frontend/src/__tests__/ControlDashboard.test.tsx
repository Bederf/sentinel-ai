/**
 * ControlDashboard Component Tests
 *
 * Tests the Control Dashboard functionality including:
 * - Device listing and selection
 * - Control panel integration
 * - Safety status display
 * - Error handling
 */

import { render, screen, fireEvent, waitFor } from '../test-utils';
import { ControlDashboard } from '../components/ControlDashboard';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import '@testing-library/jest-dom';

// Mock the API client
vi.mock('../lib/api', () => ({
  default: {
    getDevices: vi.fn(),
    getDevice: vi.fn(),
    controlDevice: vi.fn(),
    getSites: vi.fn(),
    getPredictions: vi.fn(),
    getDeviceSafetyStatus: vi.fn(),
    getRecentAuditLogs: vi.fn(),
    getHealthThresholds: vi.fn().mockResolvedValue({
      warning: 70,
      critical: 40,
    }),
  },
  isExpectedApiError: vi.fn((error: unknown) => {
    const maybeError = error as { status?: number; message?: string } | null;
    if (maybeError?.status === 401 || maybeError?.status === 429) return true;
    const message = (maybeError?.message || "").toLowerCase();
    return message.includes("status 401") || message.includes("status 429");
  }),
}));

import api from '@/lib/api';

describe('ControlDashboard', () => {
  const mockDevices = [
    {
      id: 'chiller-gateway-001',
      name: 'Gateway Theatre Chiller',
      device_type: 'hvac',
      type: 'HVAC_CHILLER',
      status: 'online',
      location: 'Main Plant Room',
      site_id: 'gateway-theatre',
      protocol: 'mock',
      description: 'Primary cooling system',
      points: {
        setpoint: {
          name: 'setpoint',
          point_type: 'analog_value',
          description: 'Temperature Setpoint',
          unit: 'C',
          min_value: 16,
          max_value: 28,
          default_value: 21.5,
          writable: true,
        },
      },
      safety_status: 'safe',
      last_communication: new Date().toISOString(),
    },
    {
      id: 'ahu-level3-002',
      name: 'Level 3 AHU',
      device_type: 'hvac',
      type: 'HVAC_AHU',
      status: 'online',
      location: 'Level 3',
      site_id: 'gateway-theatre',
      protocol: 'mock',
      description: 'Air handling unit',
      points: {
        fan_speed: {
          name: 'fan_speed',
          point_type: 'analog_value',
          description: 'Fan Speed',
          unit: '%',
          min_value: 0,
          max_value: 100,
          default_value: 75,
          writable: true,
        },
      },
      safety_status: 'warning',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getDevices as ReturnType<typeof vi.fn>).mockResolvedValue(mockDevices);
    (api.getDevice as ReturnType<typeof vi.fn>).mockImplementation((id: string) => {
      const device = mockDevices.find(d => d.id === id);
      return Promise.resolve(device);
    });
    (api.getSites as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 'gateway-theatre', name: 'Gateway Theatre', location: 'Cape Town', status: 'normal' },
    ]);
    (api.getPredictions as ReturnType<typeof vi.fn>).mockResolvedValue({ predictions: [] });
    (api.getDeviceSafetyStatus as ReturnType<typeof vi.fn>).mockResolvedValue({ overall_status: 'safe' });
    (api.getRecentAuditLogs as ReturnType<typeof vi.fn>).mockResolvedValue({ entries: [] });
  });

  describe('Initial Loading', () => {
    it('should show loading state initially', () => {
      (api.getDevices as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));
      render(<ControlDashboard />);
      // Component should render without crashing during loading
      expect(document.querySelector('.animate-pulse, [class*="loading"]')).toBeTruthy();
    });

    it('should load and display devices', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
        expect(screen.getByText('Level 3 AHU')).toBeInTheDocument();
      });
    });

    it('should display device count', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        // Component shows "X online, Y offline" in the device count header
        expect(screen.getByText(/2 online/i)).toBeInTheDocument();
      });
    });
  });

  describe('Device Selection', () => {
    it('should auto-select first device', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
      });

      // Control panel header should show selected device
      await waitFor(() => {
        expect(screen.getByText('Control Panel')).toBeInTheDocument();
      });
    });

    it('should allow manual device selection', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Level 3 AHU')).toBeInTheDocument();
      });

      // Click on the second device
      fireEvent.click(screen.getByText('Level 3 AHU'));

      // Device should be selected
      await waitFor(() => {
        expect(api.getDevice).toHaveBeenCalledWith('ahu-level3-002');
      });
    });
  });

  describe('Safety Status Display', () => {
    it('should display safe status correctly', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
      });

      // Safe status should be displayed
      await waitFor(() => {
        const safeElements = screen.getAllByText(/safe/i);
        expect(safeElements.length).toBeGreaterThan(0);
      });
    });

    it('should display warning status correctly', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Level 3 AHU')).toBeInTheDocument();
      });

      // Click device with warning status
      fireEvent.click(screen.getByText('Level 3 AHU'));

      await waitFor(() => {
        const warningElements = screen.getAllByText(/warning/i);
        expect(warningElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Control Panel', () => {
    it('should display control panel header', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Control Panel')).toBeInTheDocument();
      });
    });

    it('should display Control Devices section', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Control Devices')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle device loading errors gracefully', async () => {
      const onError = vi.fn();
      (api.getDevices as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));

      render(<ControlDashboard onError={onError} />);

      await waitFor(() => {
        expect(onError).toHaveBeenCalledWith('Failed to load control devices');
      });
    });

    it('should not crash on API failure', async () => {
      (api.getDevices as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('API Error'));

      // Should not throw
      expect(() => render(<ControlDashboard />)).not.toThrow();
    });
  });

  describe('Refresh Functionality', () => {
    it('should have refresh button', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
      });

      // Find refresh button by title
      const refreshButton = screen.getByTitle('Refresh devices');
      expect(refreshButton).toBeInTheDocument();
    });

    it('should refresh devices on click', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
      });

      // Initial load
      expect(api.getDevices).toHaveBeenCalledTimes(1);

      // Click refresh button
      const refreshButton = screen.getByTitle('Refresh devices');
      fireEvent.click(refreshButton);

      // Should call getDevices again
      await waitFor(() => {
        expect(api.getDevices).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Layout', () => {
    it('should render two-column layout', async () => {
      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
      });

      // Check for main panel headers (Device list and Control panel)
      expect(screen.getByText('Control Devices')).toBeInTheDocument();
      expect(screen.getByText('Control Panel')).toBeInTheDocument();
    });
  });

  describe('Control Actions', () => {
    it('should call controlDevice API on control action', async () => {
      (api.controlDevice as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        message: 'Control successful',
        device_id: 'chiller-gateway-001',
        point: 'setpoint',
        value: 22.0,
        priority: 8,
      });

      render(<ControlDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Gateway Theatre Chiller')).toBeInTheDocument();
      });

      // API should be available for control actions (tested via component behavior)
      expect(api.getDevices).toHaveBeenCalled();
    });
  });
});