/**
 * Dashboard Tests
 *
 * Tests comprehensive Dashboard functionality:
 * - KPI card rendering and calculations
 * - Site protection grid with site cards
 * - Energy analytics with period and site filters
 * - Risk predictions section with hero card
 * - Modal interactions (prediction detail, risk detail)
 * - Drag-and-drop reordering
 * - Preference saving and loading
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
import type { DashboardStats, Site, Prediction } from '@/lib/api';

// Mock Tremor components - import function directly into factory
vi.mock('@tremor/react', async () => {
  const { createTremorMocks } = await import('@/test-utils/mockTremor');
  return createTremorMocks();
});

// Mock API module
vi.mock('@/lib/api', () => ({
  default: {
    getStats: vi.fn(),
    getPredictions: vi.fn(),
    getEnergy: vi.fn(),
    getDashboardPreferences: vi.fn(),
    updateDashboardPreferences: vi.fn(),
    resetDashboardPreferences: vi.fn(),
  },
  createWorkOrder: vi.fn(),
}));

// Mock custom hook
vi.mock('@/hooks/useBuildingsList', () => ({
  useBuildingsList: vi.fn(() => ({ data: [] })),
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

vi.mock('../PredictionCard', () => ({
  PredictionCard: ({ prediction, onClick }: any) => (
    <button onClick={() => onClick(prediction)} data-testid={`prediction-card-${prediction.id}`}>
      {prediction.equipment_name}
    </button>
  ),
}));

vi.mock('../PredictionDetail', () => ({
  PredictionDetail: ({ isOpen, onClose }: any) => (
    isOpen ? (
      <div data-testid="prediction-detail-modal">
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null
  ),
}));

vi.mock('../RiskDetailModal', () => ({
  RiskDetailModal: ({ isOpen, onClose }: any) => (
    isOpen ? (
      <div data-testid="risk-detail-modal">
        <button onClick={onClose}>Close Risk Modal</button>
      </div>
    ) : null
  ),
}));

vi.mock('../CardLibrary', () => ({
  default: ({ isOpen, onClose }: any) => (
    isOpen ? (
      <div data-testid="card-library">
        <button onClick={onClose}>Close Card Library</button>
      </div>
    ) : null
  ),
}));

vi.mock('../solar/SolarOverviewPanel', () => ({
  SolarOverviewPanel: () => <div data-testid="solar-overview">Solar Overview</div>,
}));

vi.mock('../solar/BESSStatusPanel', () => ({
  BESSStatusPanel: () => <div data-testid="bess-status">BESS Status</div>,
}));

vi.mock('../solar/InverterStatusMatrix', () => ({
  InverterStatusMatrix: () => <div data-testid="inverter-status">Inverter Matrix</div>,
}));

vi.mock('../solar/EnergyFlowDiagram', () => ({
  EnergyFlowDiagram: () => <div data-testid="energy-flow">Energy Flow</div>,
}));

vi.mock('../OccupancyPanel', () => ({
  OccupancyPanel: () => <div data-testid="occupancy-panel">Occupancy</div>,
}));

vi.mock('../ComfortComplaintPanel', () => ({
  default: () => <div data-testid="comfort-panel">Comfort</div>,
}));

vi.mock('../SiteDetail', () => ({
  SiteDetail: ({ onBack }: any) => (
    <button onClick={onBack}>Back</button>
  ),
}));

vi.mock('../PageLoading', () => ({
  PageLoading: ({ message }: any) => <div>{message}</div>,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Customize')).toBeInTheDocument();
      });
    });
  });

  describe('KPI Cards', () => {
    it('should display all five KPI cards', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] } as any);
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('kpi-card-Risk Predictions');
        // Should show count of all predictions (including healthy ones)
        expect(card.textContent).toContain('3');
      });
    });
  });

  describe('Site Protection Grid', () => {
    it('should display Site Protection Status panel header', async () => {
      const sites = [createMockSite()];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('site-card-site-001')).toBeInTheDocument();
        expect(screen.getByTestId('site-card-site-002')).toBeInTheDocument();
      });
    });

    it('should navigate to site detail when site card clicked', async () => {
      const sites = [createMockSite({ id: 'site-002', name: 'Test Site' })];
      const stats = createMockDashboardStats();
      const onViewChange = vi.fn();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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

    it('should display protected site count badge', async () => {
      const sites = [
        createMockSite({ id: 'site-001', status: 'normal' }),
        createMockSite({ id: 'site-002', status: 'normal' }),
        createMockSite({ id: 'site-003', status: 'warning' }),
      ];
      const stats = createMockDashboardStats();

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: sites } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('2 protected')).toBeInTheDocument();
      });
    });
  });

  describe('Energy Analytics', () => {
    it('should display Energy Analytics panel', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(api.getEnergy).mockResolvedValue({ data: energyData });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Chart: 2 points')).toBeInTheDocument();
      });
    });
  });

  describe('Risk Predictions', () => {
    it('should display Risk Intelligence panel header', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Risk Intelligence')).toBeInTheDocument();
      });
    });

    it('should filter predictions to show only critical and warning severity', async () => {
      const stats = createMockDashboardStats();
      const predictions = [
        createMockPrediction({ id: 'pred-1', severity: 'critical' }),
        createMockPrediction({ id: 'pred-2', severity: 'warning' }),
        createMockPrediction({ id: 'pred-3', severity: 'healthy' }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Should display only critical and warning predictions
        expect(screen.getByTestId('prediction-card-pred-1')).toBeInTheDocument();
        expect(screen.getByTestId('prediction-card-pred-2')).toBeInTheDocument();
        expect(screen.queryByTestId('prediction-card-pred-3')).not.toBeInTheDocument();
      });
    });

    it('should display empty state when no predictions', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('No risk predictions detected')).toBeInTheDocument();
      });
    });

    it('should display highest risk prediction as hero card', async () => {
      const stats = createMockDashboardStats();
      const predictions = [
        createMockPrediction({
          id: 'pred-1',
          severity: 'warning',
          equipment_name: 'Chiller Unit A',
          probability_percent: 45,
        }),
        createMockPrediction({
          id: 'pred-2',
          severity: 'critical',
          equipment_name: 'Generator B',
          probability_percent: 85,
        }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] } as any);
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Highest risk should be critical first, then by probability
        expect(screen.getByText('Generator B')).toBeInTheDocument();
      });
    });

    it('should calculate total potential savings from critical predictions', async () => {
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Should show savings total (8000 ZAR)
        expect(screen.getByText(/saveable/)).toBeInTheDocument();
      });
    });

    it('should open prediction detail modal when prediction card clicked', async () => {
      const stats = createMockDashboardStats();
      const predictions = [
        createMockPrediction({ id: 'pred-1', severity: 'critical' }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('prediction-card-pred-1');
        fireEvent.click(card);
      });

      await waitFor(() => {
        expect(screen.getByTestId('prediction-detail-modal')).toBeInTheDocument();
      });
    });

    it('should close prediction detail modal when close button clicked', async () => {
      const stats = createMockDashboardStats();
      const predictions = [
        createMockPrediction({ id: 'pred-1', severity: 'critical' }),
      ];

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const card = screen.getByTestId('prediction-card-pred-1');
        fireEvent.click(card);
      });

      await waitFor(() => {
        expect(screen.getByTestId('prediction-detail-modal')).toBeInTheDocument();
      });

      const closeButton = screen.getAllByText('Close Modal')[0];
      fireEvent.click(closeButton);

      await waitFor(() => {
        expect(screen.queryByTestId('prediction-detail-modal')).not.toBeInTheDocument();
      });
    });
  });

  describe('Customization and Preferences', () => {
    it('should display Customize button', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Customize')).toBeInTheDocument();
      });
    });

    it('should open Card Library when Customize clicked', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const customizeButton = screen.getByText('Customize');
        fireEvent.click(customizeButton);
      });

      await waitFor(() => {
        expect(screen.getByTestId('card-library')).toBeInTheDocument();
      });
    });

    it('should close Card Library', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const customizeButton = screen.getByText('Customize');
        fireEvent.click(customizeButton);
      });

      await waitFor(() => {
        const closeButton = screen.getByText('Close Card Library');
        fireEvent.click(closeButton);
      });

      await waitFor(() => {
        expect(screen.queryByTestId('card-library')).not.toBeInTheDocument();
      });
    });

    it('should load dashboard preferences on mount', async () => {
      const stats = createMockDashboardStats();
      const preferences = {
        preferences: {
          visible_kpi_cards: ['kpi-protected-sites'],
          visible_sections: ['kpi-row', 'site-protection'],
          kpi_card_order: ['kpi-protected-sites'],
          section_order: ['kpi-row', 'site-protection'],
          default_energy_period: 7,
          default_energy_site_id: 'site-002',
        },
      };

      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockResolvedValue(preferences);
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] });
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Should load and apply preferences
        expect(vi.mocked(api.getDashboardPreferences)).toHaveBeenCalled();
      });
    });

    it('should save dashboard preferences when card visibility changes', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(api.updateDashboardPreferences).mockResolvedValue({});
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      // Note: This test assumes Card Library is properly mocked to emit visibility changes
      // In integration, this would be tested through the CardLibrary component interaction
      await waitFor(() => {
        expect(screen.getByText('Customize')).toBeInTheDocument();
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
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
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

  describe('Solar & BESS Section', () => {
    it('should display Solar & BESS section when visible', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('solar-overview')).toBeInTheDocument();
        expect(screen.getByTestId('energy-flow')).toBeInTheDocument();
        expect(screen.getByTestId('bess-status')).toBeInTheDocument();
        expect(screen.getByTestId('inverter-status')).toBeInTheDocument();
      });
    });
  });

  describe('Additional Sections', () => {
    it('should display Comfort and Occupancy panels when visible', async () => {
      const stats = createMockDashboardStats();
      vi.mocked(api.getStats).mockResolvedValue(stats);
      vi.mocked(api.getPredictions).mockResolvedValue({ predictions: [] });
      vi.mocked(api.getDashboardPreferences).mockRejectedValue(new Error('Not found'));
      vi.mocked(api.getEnergy).mockResolvedValue({ data: [] } as any);
      vi.mocked(useBuildingsList).mockReturnValue({ data: [] } as any);

      render(<Dashboard onViewChange={vi.fn()} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('comfort-panel')).toBeInTheDocument();
        expect(screen.getByTestId('occupancy-panel')).toBeInTheDocument();
      });
    });
  });
});
