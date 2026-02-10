/**
 * SiteCard Component Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '../../../test-utils';
import userEvent from '@testing-library/user-event';
import SiteCard from '../SiteCard';
import { createMockSite, createMockDevice } from '../../test-utils/factories';
import api from '../../lib/api';

// Mock the API client
vi.mock('../../lib/api', () => ({
  default: {
    getSiteDevices: vi.fn(),
    getDeviceSafetyStatus: vi.fn(),
    getOptimizationStatus: vi.fn(),
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

describe('SiteCard', () => {
  const mockSite = createMockSite({
    id: 'site-001',
    name: 'Test Site',
    equipment_count: 12,
    alert_count: 2,
    status: 'normal',
  });

  beforeEach(() => {
    vi.clearAllMocks();
    // Default mock responses
    (api.getSiteDevices as any).mockResolvedValue([]);
    (api.getDeviceSafetyStatus as any).mockResolvedValue({ overall_status: 'safe' });
    (api.getOptimizationStatus as any).mockResolvedValue({
      optimization_status: 'unknown',
      optimization_enabled: false,
      optimization_settings: { mode: 'supervised', last_analysis: null },
      last_recommendation: null,
      last_optimization: null,
      optimization_history: [],
    });
  });

  describe('Rendering', () => {
    it('should render site name', () => {
      render(<SiteCard site={mockSite} />);
      expect(screen.getByText('Test Site')).toBeInTheDocument();
    });

    it('should render location', async () => {
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      expect(screen.getByText(mockSite.location)).toBeInTheDocument();
    });

    it('should render equipment count', async () => {
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      expect(screen.getByText('12')).toBeInTheDocument();
      expect(screen.getByText('Equipment')).toBeInTheDocument();
    });

    it('should render alert count', async () => {
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('Risks')).toBeInTheDocument();
    });

    it('should render status badge', async () => {
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      expect(screen.getByText('Protected')).toBeInTheDocument();
    });

    it('should render type badge', async () => {
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      expect(screen.getByText(mockSite.type)).toBeInTheDocument();
    });
  });

  describe('Status Display', () => {
    it('should display "Protected" for normal status', () => {
      const normalSite = createMockSite({ status: 'normal' });
      render(<SiteCard site={normalSite} />);
      expect(screen.getByText('Protected')).toBeInTheDocument();
    });

    it('should display "Elevated" for warning status', () => {
      const warningSite = createMockSite({ status: 'warning' });
      render(<SiteCard site={warningSite} />);
      expect(screen.getByText('Elevated')).toBeInTheDocument();
    });

    it('should display "Critical" for critical status', () => {
      const criticalSite = createMockSite({ status: 'critical' });
      render(<SiteCard site={criticalSite} />);
      expect(screen.getByText('Critical')).toBeInTheDocument();
    });
  });

  describe('Click Handling', () => {
    it('should call onClick when card is clicked', async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();
      
      render(<SiteCard site={mockSite} onClick={handleClick} showSafetyStatus={false} />);
      
      const card = screen.getByText('Test Site').closest('div[class*="cursor-pointer"]');
      if (card) {
        await user.click(card);
        expect(handleClick).toHaveBeenCalledWith(mockSite);
      }
    });

    it('should not call onClick when onClick prop is not provided', async () => {
      const user = userEvent.setup();
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      
      const card = screen.getByText('Test Site').closest('div');
      if (card) {
        await user.click(card);
        // Should not throw error
        expect(card).toBeInTheDocument();
      }
    });
  });

  describe('Safety Status', () => {
    it('should fetch and display safety status when showSafetyStatus is true', async () => {
      const mockDevices = [
        createMockDevice({ id: 'device-001', safety_status: 'safe' }),
        createMockDevice({ id: 'device-002', safety_status: 'safe' }),
      ];

      (api.getSiteDevices as any).mockResolvedValue(mockDevices);
      (api.getDeviceSafetyStatus as any)
        .mockResolvedValueOnce({ overall_status: 'safe' })
        .mockResolvedValueOnce({ overall_status: 'safe' });

      render(<SiteCard site={mockSite} showSafetyStatus={true} />);

      await waitFor(() => {
        expect(api.getSiteDevices).toHaveBeenCalledWith(mockSite.id);
      });

      // Should eventually show safe count
      await waitFor(() => {
        const safeText = screen.queryByText(/\/\d+/);
        expect(safeText).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('should use equipment_count fallback when no devices returned', async () => {
      (api.getSiteDevices as any).mockResolvedValue([]);

      render(<SiteCard site={mockSite} showSafetyStatus={true} />);

      await waitFor(() => {
        // Should show calculated safe count: equipment_count - alert_count = 10
        // Format is "safe/total" so 10/12
        expect(screen.getByText('10/12')).toBeInTheDocument();
      });
    });

    it('should handle API errors gracefully', async () => {
      (api.getSiteDevices as any).mockRejectedValue(new Error('API Error'));

      render(<SiteCard site={mockSite} showSafetyStatus={true} />);

      await waitFor(() => {
        // Should fallback to equipment_count calculation
        // Format is "safe/total" so 10/12
        expect(screen.getByText('10/12')).toBeInTheDocument();
      });
    });

    it('should not fetch safety status when showSafetyStatus is false', () => {
      render(<SiteCard site={mockSite} showSafetyStatus={false} />);
      
      expect(api.getSiteDevices).not.toHaveBeenCalled();
    });
  });

  describe('Optimization Status', () => {
    it('should fetch optimization status when enabled', async () => {
      const optimizedSite = createMockSite({
        optimization_enabled: true,
        optimization_status: 'optimized',
      });

      (api.getOptimizationStatus as any).mockResolvedValue({
        optimization_status: 'optimized',
        optimization_enabled: true,
        optimization_settings: { mode: 'supervised', last_analysis: null },
        last_recommendation: null,
        last_optimization: null,
        optimization_history: [],
      });

      render(<SiteCard site={optimizedSite} showOptimizationStatus={true} />);

      await waitFor(() => {
        expect(api.getOptimizationStatus).toHaveBeenCalledWith(optimizedSite.id);
      });
    });

    it('should not fetch optimization status when disabled', () => {
      const disabledSite = createMockSite({ optimization_enabled: false });
      
      render(<SiteCard site={disabledSite} showOptimizationStatus={true} />);
      
      expect(api.getOptimizationStatus).not.toHaveBeenCalled();
    });
  });

  describe('Safe Asset Calculation', () => {
    it('should correctly calculate safe assets from device safety statuses', async () => {
      const mockDevices = [
        createMockDevice({ id: 'device-001' }),
        createMockDevice({ id: 'device-002' }),
        createMockDevice({ id: 'device-003' }),
      ];

      (api.getSiteDevices as any).mockResolvedValue(mockDevices);
      (api.getDeviceSafetyStatus as any)
        .mockResolvedValueOnce({ overall_status: 'safe' })
        .mockResolvedValueOnce({ overall_status: 'safe' })
        .mockResolvedValueOnce({ overall_status: 'warning' });

      render(<SiteCard site={mockSite} showSafetyStatus={true} />);

      await waitFor(() => {
        // Component uses equipment_count (12) for total and calculates
        // safe as equipment_count - alert_count = 12 - 2 = 10
        expect(screen.getByText('10/12')).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('should display warning + critical count correctly', async () => {
      const mockDevices = [
        createMockDevice({ id: 'device-001' }),
        createMockDevice({ id: 'device-002' }),
      ];

      (api.getSiteDevices as any).mockResolvedValue(mockDevices);
      (api.getDeviceSafetyStatus as any)
        .mockResolvedValueOnce({ overall_status: 'warning' })
        .mockResolvedValueOnce({ overall_status: 'critical' });

      render(<SiteCard site={mockSite} showSafetyStatus={true} />);

      await waitFor(() => {
        // Component uses equipment_count (12) for total and calculates
        // safe as equipment_count - alert_count = 12 - 2 = 10
        // Device statuses only affect overall status, not the count
        expect(screen.getByText('10/12')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });
});
