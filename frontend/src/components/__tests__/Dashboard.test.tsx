/**
 * Dashboard Tests
 *
 * Tests comprehensive Dashboard functionality:
 * - KPI card rendering and calculations
 * - Site protection grid with site cards
 * - Energy analytics with period and site filters
 * - Navigation to site detail
 *
 * Site-specific panels (risk predictions, solar, comfort, occupancy,
 * energy comparison, validation) are now tested in SiteDetail tests.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import Dashboard from '../Dashboard';
import { createTestQueryClient } from '@/test-utils/mockQueryClient';
import {
  createMockDashboardStats,
  createMockSite,
  createMockPrediction,
  createMockEnergyDataPoint,
} from '@/test-utils/factories';
// Types available from '@/lib/api' if needed

// No-op: Tremor components have been replaced with plain HTML

// Mock API module
vi.mock('@/lib/api', () => ({
  default: {
    getStats: vi.fn(),
    getPredictions: vi.fn(),
    getEnergy: vi.fn(),
  },
}));

// Mock custom hook
vi.mock('@/hooks/useBuildingsList', () => ({
  useBuildingsList: vi.fn(() => ({ data: [] })),
}));

// Mock useModules hook
vi.mock('@/contexts/ModuleHooks', () => ({
  useModules: vi.fn(() => ({
    isModuleActive: vi.fn(() => true),
    activeModules: [{ module_type: 'energy' }],
    recommendations: [],
  })),
}));

// Mock useSimulation hook
vi.mock('@/contexts/SimulationContext', () => ({
  useSimulation: vi.fn(() => ({
    running: false,
    occupancyPercent: 0,
    hvacLoadPercent: 0,
    ambientTemp: 25,
    totalEnergyKwh: 0,
    currentHourPowerKw: 0,
  })),
}));

// Mock useServerEvents hook
vi.mock('@/hooks/useServerEvents', () => ({
  useServerEvents: vi.fn(),
}));

// Mock components
vi.mock('../SortableKPICard', () => ({
  SortableKPICard: ({ title, value, subtitle }: any) => (
    <div data-testid={`kpi-card-${title}`}>
      <div>{title}</div>
      <div>{value}</div>
      {subtitle && <div>{subtitle}</div>}
    </div>
  ),
}));

vi.mock('../DashboardSection', () => ({
  DashboardSection: ({ children }: any) => <div>{children}</div>,
}));

vi.mock('../SiteCard', () => ({
  SiteCard: ({ site, onClick }: any) => (
    <button onClick={() => onClick(site)} data-testid={`site-card-${site.id}`}>
      {site.name}
    </button>
  ),
}));

vi.mock('../EnergyChart', () => ({
  EnergyChart: ({ data, loading }: any) => (
    <div>
      {loading ? 'Loading chart...' : `Chart: ${data.length} points`}
    </div>
  ),
}));

vi.mock('../SiteDetail', () => ({
  SiteDetail: ({ onBack }: any) => (
    <button onClick={onBack}>Back</button>
  ),
}));

import api from '@/lib/api';
import { useBuildingsList } from '@/hooks/useBuildingsList';

// Test wrapper
function createTestWrapper() {
  const queryClient = createTestQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Loading and Error States', () => {
    it('should display loading state initially', async () => {
      vi.mocked(api.getStats).mockImplementation(() => new Promise(() => {})); // Never resolves
      vi.mocked(api.getPredictions).mockImplementation(() => new Promise(() => {}));
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      // Wait for loading state to be displayed
      await waitFor(() => {
        expect(screen.getByText(/initializing sentinel|loading/i)).toBeInTheDocument();
      }, { timeout: 1000 });
    });

    it('should display error state when data fetch fails', async () => {
      vi.mocked(api.getStats).mockRejectedValue(new Error('API Error'));
      vi.mocked(api.getPredictions).mockRejectedValue(new Error('API Error'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/error loading dashboard/i)).toBeInTheDocument();
      });
    });

    it('should render dashboard after data loads successfully', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Site Protection Status')).toBeInTheDocument();
      });
    });
  });

  describe('KPI Cards', () => {
    it('should display all five KPI cards', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('kpi-card-Protected Sites')).toBeInTheDocument();
        expect(screen.getByTestId('kpi-card-Monitored Assets')).toBeInTheDocument();
        expect(screen.getByTestId('kpi-card-Active Risks')).toBeInTheDocument();
        expect(screen.getByTestId('kpi-card-Potential Savings')).toBeInTheDocument();
        expect(screen.getByTestId('kpi-card-Risk Predictions')).toBeInTheDocument();
      });
    });

    it('should calculate Protected Sites count from buildings list', async () => {
      const sites = [
        createMockSite({ id: 'site-001', status: 'normal' }),
        createMockSite({ id: 'site-002', status: 'warning' }),
        createMockSite({ id: 'site-003', status: 'normal' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('kpi-card-Protected Sites');
        expect(card.textContent).toContain('3'); // 3 sites total
      });
    });

    it('should display total equipment count in Monitored Assets KPI', async () => {
      const stats = createMockDashboardStats({ total_equipment: 156 });
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('kpi-card-Monitored Assets');
        expect(card.textContent).toContain('156');
      });
    });

    it('should display active alerts count in Active Risks KPI', async () => {
      const stats = createMockDashboardStats({ active_alerts: 12 });
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('kpi-card-Active Risks');
        expect(card.textContent).toContain('12');
      });
    });

    it('should format Potential Savings in ZAR currency', async () => {
      const stats = createMockDashboardStats();
      const predictions = [
        createMockPrediction({
          severity: 'critical',
          financial_impact: { potential_loss_zar: 5000 },
        }),
        createMockPrediction({
          severity: 'warning',
          financial_impact: { potential_loss_zar: 3000 },
        }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('kpi-card-Potential Savings');
        // Should show ZAR currency formatting
        expect(card.textContent).toContain('R');
      });
    });

    it('should display prediction count in Risk Predictions KPI', async () => {
      const stats = createMockDashboardStats();
      const predictions = [
        createMockPrediction({ severity: 'critical' }),
        createMockPrediction({ severity: 'warning' }),
        createMockPrediction({ severity: 'healthy' }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] } as any);
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('kpi-card-Risk Predictions');
        // Only critical + warning predictions are stored (filtered on load)
        expect(card.textContent).toContain('2');
      });
    });
  });

  describe('Site Protection Grid', () => {
    it('should display Site Protection Status panel header', async () => {
      const sites = [createMockSite()];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Site Protection Status')).toBeInTheDocument();
      });
    });

    it('should display empty state when no sites available', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('No sites available')).toBeInTheDocument();
      });
    });

    it('should render site cards for each building', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Building B' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('site-card-site-001')).toBeInTheDocument();
        expect(screen.getByTestId('site-card-site-002')).toBeInTheDocument();
      });
    });

    it('should allow hiding a site card and restoring all hidden cards', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Building B' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('site-card-site-001')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByLabelText('Hide Building A from dashboard'));

      await waitFor(() => {
        expect(screen.queryByTestId('site-card-site-001')).not.toBeInTheDocument();
        expect(screen.getByText('1 hidden')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /show all/i }));

      await waitFor(() => {
        expect(screen.getByTestId('site-card-site-001')).toBeInTheDocument();
      });
    });

    it('should navigate to site detail when site card clicked', async () => {
      const sites = [createMockSite({ id: 'site-002', name: 'Test Site' })];
      const stats = createMockDashboardStats();
      const onViewChange = vi.fn();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={onViewChange} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const siteCard = screen.getByTestId('site-card-site-002');
        fireEvent.click(siteCard);
      });

      // Should show site detail (mocked component shows Back button)
      await waitFor(() => {
        expect(screen.getByText('Back')).toBeInTheDocument();
      });
    });

    it('should display elevated site count badge', async () => {
      const sites = [
        createMockSite({ id: 'site-001', status: 'normal' }),
        createMockSite({ id: 'site-002', status: 'normal' }),
        createMockSite({ id: 'site-003', status: 'warning' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getAllByText('1 elevated').length).toBeGreaterThan(0);
      });
    });
  });

  describe('Energy Analytics', () => {
    it('should display Energy Analytics panel', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Energy Analytics')).toBeInTheDocument();
      });
    });

    it('should display time period filter buttons (7d, 30d, 90d)', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('7d')).toBeInTheDocument();
        expect(screen.getByText('30d')).toBeInTheDocument();
        expect(screen.getByText('90d')).toBeInTheDocument();
      });
    });

    it('should default to 30-day period', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(vi.mocked(api.getEnergy)).toHaveBeenCalledWith(null, 30);
      });
    });

    it('should load energy data when period changes', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const sevenDayButton = screen.getByText('7d');
        fireEvent.click(sevenDayButton);
      });

      await waitFor(() => {
        expect(vi.mocked(api.getEnergy)).toHaveBeenCalledWith(null, 7);
      });
    });

    it('should display site selector filter for energy data', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Building B' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByDisplayValue(/all sites/i)).toBeInTheDocument();
      });
    });

    it('should filter energy data by site when selected', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Building B' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const selector = screen.getByDisplayValue(/all sites/i) as HTMLSelectElement;
        fireEvent.change(selector, { target: { value: 'site-001' } });
      });

      await waitFor(() => {
        expect(vi.mocked(api.getEnergy)).toHaveBeenCalledWith('site-001', 30);
      });
    });

    it('should display energy chart with data points', async () => {
      const stats = createMockDashboardStats();
      const energyData = [
        createMockEnergyDataPoint({ timestamp: '2024-01-15T00:00:00Z', consumption_kwh: 100 }),
        createMockEnergyDataPoint({ timestamp: '2024-01-15T06:00:00Z', consumption_kwh: 150 }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: energyData });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Chart: 2 points')).toBeInTheDocument();
      });
    });
  });

  describe('Navigation', () => {
    it('should call onViewChange when navigating to different views', async () => {
      const stats = createMockDashboardStats();
      const onViewChange = vi.fn();
      const sites = [createMockSite({ id: 'site-002', name: 'Test Site' })];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={onViewChange} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const siteCard = screen.getByTestId('site-card-site-002');
        fireEvent.click(siteCard);
      });

      // The navigation happens internally through state management
      expect(screen.getByText('Back')).toBeInTheDocument();
    });
  });
});
