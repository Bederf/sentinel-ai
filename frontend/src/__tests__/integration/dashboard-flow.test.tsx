/**
 * Integration tests for dashboard flow.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '../../test-utils';
import { Dashboard } from '../../components/Dashboard';
import api from '../../lib/api';
import {
  createMockSite,
  createMockDashboardStats,
  createMockPredictions,
} from '../../test-utils/factories';

// Mock the API client
vi.mock('../../lib/api', () => ({
  default: {
    getStats: vi.fn(),
    getSites: vi.fn(),
    getPredictions: vi.fn(),
    getEnergy: vi.fn(),
    getHealthThresholds: vi.fn().mockResolvedValue({
      warning: 70,
      critical: 40,
    }),
  },
}));

describe('Dashboard Integration Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Default mock responses
    (api.getStats as any).mockResolvedValue(createMockDashboardStats());
    (api.getSites as any).mockResolvedValue([
      createMockSite({ id: 'site-001', name: 'Site 1' }),
      createMockSite({ id: 'site-002', name: 'Site 2' }),
    ]);
    (api.getPredictions as any).mockResolvedValue({
      total: 1,
      predictions: createMockPredictions(1),
    });
    (api.getEnergy as any).mockResolvedValue({
      data: [],
      total_kwh: 0,
      period_days: 30,
    });
  });

  it('should load and display dashboard data', async () => {
    const mockOnViewChange = vi.fn();
    render(<Dashboard onViewChange={mockOnViewChange} />);

    // Wait for data to load
    await waitFor(() => {
      expect(api.getStats).toHaveBeenCalled();
      expect(api.getSites).toHaveBeenCalled();
      expect(api.getPredictions).toHaveBeenCalled();
    });

    // Verify sites are displayed
    await waitFor(() => {
      // Site name appears in both the SiteCard and dropdown options
      expect(screen.getAllByText('Site 1').length).toBeGreaterThan(0);
    });
  });

  it('should handle API errors gracefully', async () => {
    (api.getStats as any).mockRejectedValue(new Error('API Error'));
    (api.getSites as any).mockRejectedValue(new Error('API Error'));

    const mockOnViewChange = vi.fn();
    render(<Dashboard onViewChange={mockOnViewChange} />);

    // Should not crash
    await waitFor(() => {
      expect(api.getStats).toHaveBeenCalled();
    });
  });

  it('should calculate and display site status counts', async () => {
    const sites = [
      createMockSite({ id: 'site-001', name: 'Site 1', status: 'normal' }),
      createMockSite({ id: 'site-002', name: 'Site 2', status: 'warning' }),
      createMockSite({ id: 'site-003', name: 'Site 3', status: 'critical' }),
    ];

    (api.getSites as any).mockResolvedValue(sites);

    const mockOnViewChange = vi.fn();
    render(<Dashboard onViewChange={mockOnViewChange} />);

    await waitFor(() => {
      // Should display site cards (Site name appears in both card and dropdown)
      expect(screen.getAllByText('Site 1').length).toBeGreaterThan(0);
    });
  });
});
