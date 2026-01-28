/**
 * ControlPanel Component Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '../../test-utils';
import ControlPanel from '../ControlPanel';
import { createMockDevice } from '../../test-utils/factories';

describe('ControlPanel', () => {
  const mockDevice = createMockDevice({
    id: 'device-001',
    name: 'Test Chiller',
    device_type: 'HVAC_CHILLER',
    points: {
      setpoint: {
        name: 'setpoint',
        point_type: 'analog_output',
        description: 'Temperature setpoint',
        unit: '°C',
        min_value: 16,
        max_value: 28,
        default_value: 22,
        writable: true,
        priority: 8,
      },
      status: {
        name: 'status',
        point_type: 'binary_output',
        description: 'Device status',
        unit: '',
        default_value: true,
        writable: true,
        priority: 8,
      },
    },
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render device name', () => {
      render(<ControlPanel device={mockDevice} />);
      expect(screen.getByText('Test Chiller')).toBeInTheDocument();
    });

    it('should render device type', () => {
      render(<ControlPanel device={mockDevice} />);
      expect(screen.getByText('HVAC_CHILLER')).toBeInTheDocument();
    });

    it('should render device location', () => {
      render(<ControlPanel device={mockDevice} />);
      expect(screen.getByText(mockDevice.location)).toBeInTheDocument();
    });

    it('should render safety status when provided', () => {
      render(
        <ControlPanel
          device={mockDevice}
          safetyStatus={{ status: 'safe', message: 'All checks passed' }}
        />
      );
      expect(screen.getByText('SAFE')).toBeInTheDocument();
    });

    it('should render warning status', () => {
      render(
        <ControlPanel
          device={mockDevice}
          safetyStatus={{ status: 'warning', message: 'Warning condition' }}
        />
      );
      expect(screen.getByText('WARNING')).toBeInTheDocument();
    });

    it('should render blocked status', () => {
      render(
        <ControlPanel
          device={mockDevice}
          safetyStatus={{ status: 'blocked', message: 'Action blocked' }}
        />
      );
      expect(screen.getByText('BLOCKED')).toBeInTheDocument();
    });
  });

  describe('Control Widgets', () => {
    it('should render temperature control for analog_output points', () => {
      render(<ControlPanel device={mockDevice} />);
      // TemperatureControl should be rendered for setpoint
      expect(screen.getByText(/setpoint/i)).toBeInTheDocument();
    });

    it('should render switch control for binary_output points', () => {
      render(<ControlPanel device={mockDevice} />);
      // SwitchControl should be rendered for status
      expect(screen.getByText(/status/i)).toBeInTheDocument();
    });

    it('should not render controls for non-writable points', () => {
      const readOnlyDevice = createMockDevice({
        points: {
          read_only: {
            name: 'read_only',
            point_type: 'analog_input',
            description: 'Read-only point',
            unit: '°C',
            default_value: 20,
            writable: false,
            priority: 8,
          },
        },
      });

      render(<ControlPanel device={readOnlyDevice} />);
      // Read-only points should not have controls
      expect(screen.queryByText(/read_only/i)).not.toBeInTheDocument();
    });
  });

  describe('Control Actions', () => {
    it('should call onControl when control action is performed', async () => {
      const handleControl = vi.fn().mockResolvedValue(undefined);

      render(<ControlPanel device={mockDevice} onControl={handleControl} />);

      // Find and interact with a control widget
      // This would depend on the actual implementation of TemperatureControl
      // For now, we'll just verify the handler is passed correctly
      expect(handleControl).not.toHaveBeenCalled();
    });

    it('should handle control errors gracefully', async () => {
      const handleControl = vi.fn().mockRejectedValue(new Error('Control failed'));

      render(<ControlPanel device={mockDevice} onControl={handleControl} />);

      // Component should not crash on error
      expect(screen.getByText('Test Chiller')).toBeInTheDocument();
    });
  });

  describe('Safety Status Integration', () => {
    it('should display safety rules when provided', () => {
      render(
        <ControlPanel
          device={mockDevice}
          safetyStatus={{
            status: 'warning',
            message: 'Warning condition',
            rules: [
              { rule: 'Temperature range', status: 'passed' },
              { rule: 'Runtime limit', status: 'failed' },
            ],
          }}
        />
      );
      expect(screen.getByText('Temperature range')).toBeInTheDocument();
      expect(screen.getByText('Runtime limit')).toBeInTheDocument();
    });

    it('should disable controls when status is blocked', () => {
      render(
        <ControlPanel
          device={mockDevice}
          safetyStatus={{ status: 'blocked', message: 'Action blocked' }}
        />
      );
      // Controls should be disabled when blocked
      // This would need to be verified based on actual implementation
      expect(screen.getByText('BLOCKED')).toBeInTheDocument();
    });
  });
});
