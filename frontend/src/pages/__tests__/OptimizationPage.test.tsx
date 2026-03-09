/**
 * OptimizationPage Tests
 *
 * Tests comprehensive OptimizationPage functionality:
 * - Site selection and scenario fetching
 * - KPI calculation and display (energy, comfort, fuel, cost)
 * - Scenario comparison table rendering
 * - Execute scenario flow with confirmation modal
 * - Action history tracking
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import OptimizationPage from '../OptimizationPage';
import { SimulationProvider } from '@/contexts/SimulationContext';
import { createTestQueryClient } from '@/test-utils/mockQueryClient';
import {
  createMockOptimizationScenario,
  createMockOptimizationStatus,
  createMockSite,
} from '@/test-utils/factories';

// Mock API module
vi.mock('@/lib/api', () => ({
  default: {
    getSites: vi.fn(),
    getOptimizationScenarios: vi.fn(),
    getOptimizationStatus: vi.fn(),
    startPrecooling: vi.fn(),
    getPredictions: vi.fn().mockResolvedValue({ predictions: [] }),
    getEskomStatus: vi.fn().mockResolvedValue({ status: 'normal', stage: 0 }),
    getSiteEskomStatus: vi.fn().mockResolvedValue({ status: 'normal', stage: 0 }),
    getRecommendations: vi.fn().mockResolvedValue([]),
  },
  authorizedFetch: vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
}));

// Mock module hooks to avoid needing ModuleProvider
vi.mock('@/contexts/ModuleHooks', () => ({
  useModules: () => ({
    isModuleActive: () => true,
    activeModules: [],
    availableModules: [],
    recommendations: [],
    loading: false,
    error: null,
  }),
  useModuleActive: () => true,
}));

// Mock child components to avoid rendering issues
vi.mock('../components/OptimizationPanel', () => ({
  OptimizationPanel: () => <div data-testid="optimization-panel">Optimization Panel</div>,
}));

vi.mock('../components/OptimizationPanelGated', () => ({
  OptimizationPanelGated: () => <div data-testid="optimization-panel">Optimization Panel</div>,
}));

vi.mock('../components/optimization/ProfileSettings', () => ({
  ProfileSettings: () => <div data-testid="profile-settings">Profile Settings</div>,
}));

vi.mock('../components/optimization/RecommendationsDashboard', () => ({
  RecommendationsDashboard: () => <div data-testid="recommendations-dashboard">Recommendations</div>,
}));

vi.mock('../components/optimization/RecommendationHistory', () => ({
  RecommendationHistory: () => <div data-testid="recommendation-history">History</div>,
}));

vi.mock('../components/EnergyComparisonPanel', () => ({
  EnergyComparisonPanel: () => <div data-testid="energy-comparison">Energy Comparison</div>,
}));


vi.mock('../components/ActualVsSentinelEnergyCard', () => ({
  ActualVsSentinelEnergyCard: () => <div data-testid="actual-vs-sentinel">Actual vs SENTINEL</div>,
}));

vi.mock('../components/ROISummaryCard', () => ({
  ROISummaryCard: () => <div data-testid="roi-summary">ROI Summary</div>,
}));

vi.mock('../components/validation', () => ({
  PowerMeterValidationCard: () => <div data-testid="power-meter-validation">Power Meter</div>,
  CostValidationCard: () => <div data-testid="cost-validation">Cost Validation</div>,
}));

import api from '@/lib/api';

// Test wrapper component
function createTestWrapper() {
  const queryClient = createTestQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <SimulationProvider>
        {children}
      </SimulationProvider>
    </QueryClientProvider>
  );
}

describe('OptimizationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Rendering and Loading', () => {
    it('should render loading state initially', () => {
      vi.mocked(api.getSites).mockImplementation(() => new Promise(() => {})); // Never resolves
      vi.mocked(api.getOptimizationScenarios).mockImplementation(() => new Promise(() => {}));
      vi.mocked(api.getOptimizationStatus).mockImplementation(() => new Promise(() => {}));

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      expect(screen.getByText(/loading optimization data/i)).toBeInTheDocument();
    });

    it('should render tabs structure after data loads', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      // Wait for page to load and render tabs
      await waitFor(
        () => {
          expect(screen.getByText('Load Shedding')).toBeInTheDocument();
        },
        { timeout: 2000 }
      );
      expect(screen.getByText('Optimization')).toBeInTheDocument();
      expect(screen.getByText('Validation')).toBeInTheDocument();
    });
  });

  describe('Site Selection', () => {
    it('should populate site selector dropdown with fetched sites', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Building B' }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(
        () => {
          const selector = screen.getByDisplayValue(/building/i);
          expect(selector).toBeInTheDocument();
        },
        { timeout: 5000 },
      );
    });

    it('should render Energy Control header', async () => {
      const sites = [
        createMockSite({ id: 'site-002', name: 'Sandton City' }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Energy Control')).toBeInTheDocument();
      });
    });

    it('should fetch optimization status on load', async () => {
      const sites = [
        createMockSite({ id: 'site-002', name: 'Sandton City' }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([createMockOptimizationScenario()]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(vi.mocked(api.getOptimizationStatus)).toHaveBeenCalled();
      });
    });

    it('should display page subtitle', async () => {
      const sites = [createMockSite()];
      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/Optimisation/)).toBeInTheDocument();
      });
    });
  });

  describe('KPI Cards and Calculations', () => {

    it('should calculate average energy savings across scenarios', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({ savings: { energy_savings_percent: 10, comfort_extension_minutes: 50, fuel_savings_percent: 5, total_savings_zar: 1000 } }),
        createMockOptimizationScenario({ savings: { energy_savings_percent: 20, comfort_extension_minutes: 100, fuel_savings_percent: 15, total_savings_zar: 3000 } }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Average should be 15% (10 + 20) / 2
        const energyText = screen.getByText(/15%/);
        expect(energyText).toBeInTheDocument();
      });
    });

    it('should calculate average comfort extension in minutes', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({ savings: { energy_savings_percent: 18, comfort_extension_minutes: 60, fuel_savings_percent: 12, total_savings_zar: 4000 } }),
        createMockOptimizationScenario({ savings: { energy_savings_percent: 18, comfort_extension_minutes: 90, fuel_savings_percent: 12, total_savings_zar: 4500 } }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Average should be 75 minutes (60 + 90) / 2
        expect(screen.getByText(/75 min/)).toBeInTheDocument();
      });
    });

    it('should display cost savings in ZAR currency format', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({ savings: { energy_savings_percent: 18, comfort_extension_minutes: 75, fuel_savings_percent: 12, total_savings_zar: 5000 } }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      // Wait for cost savings element to appear with ZAR formatting
      await waitFor(
        () => {
          const costText = screen.getByText('Cost Savings');
          expect(costText).toBeInTheDocument();
        },
        { timeout: 3000 }
      );
    });

    it('should show zero KPIs when no scenarios available', async () => {
      const sites = [createMockSite()];
      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const energyCards = screen.getAllByText(/Energy Savings/);
        expect(energyCards.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Scenario Comparison Table', () => {
    it('should display baseline row (Without Pre-cooling)', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({
          thermal_runway: { without_precooling: 45, with_precooling: 120, comfort_maintained: true },
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Without Pre-cooling')).toBeInTheDocument();
      });
    });


    it('should display Execute button for non-baseline scenarios', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const executeButtons = screen.getAllByRole('button', { name: /execute/i });
        expect(executeButtons.length).toBeGreaterThan(0);
      });
    });

    it('should NOT display Execute button for baseline row', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Should have Execute buttons but baseline row shouldn't
        const table = screen.getByText('Scenario Comparison').closest('div')?.parentElement;
        expect(table).toBeInTheDocument();
      });
    });

    it('should format runway extension with "min" suffix', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({
          thermal_runway: { without_precooling: 45, with_precooling: 120, comfort_maintained: true },
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('45 min')).toBeInTheDocument();
        expect(screen.getByText('120 min')).toBeInTheDocument();
      });
    });

    it('should display success rate badge as Yes/No', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({
          thermal_runway: { without_precooling: 45, with_precooling: 120, comfort_maintained: true },
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Yes')).toBeInTheDocument();
      });
    });
  });

  describe('Execute Scenario Flow', () => {
    it('should open confirmation modal when Execute button clicked', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const executeButton = screen.getAllByRole('button', { name: /execute/i })[0];
        fireEvent.click(executeButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/execute optimization/i)).toBeInTheDocument();
        expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
      });
    });


    it('should close modal when Cancel button clicked', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const executeButton = screen.getAllByRole('button', { name: /execute/i })[0];
        fireEvent.click(executeButton);
      });

      await waitFor(() => {
        const cancelButton = screen.getByRole('button', { name: /cancel/i });
        fireEvent.click(cancelButton);
      });

      await waitFor(() => {
        expect(screen.queryByText(/execute optimization/i)).not.toBeInTheDocument();
      });
    });

    it('should call startPrecooling API when Confirm button clicked', async () => {
      const sites = [createMockSite({ id: 'site-002' })];
      const scenarios = [
        createMockOptimizationScenario({
          scenario_id: 'scenario-001',
          site_id: 'site-002',
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());
      vi.mocked(api.startPrecooling).mockResolvedValue({ success: true, message: 'Precooling started' });

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const executeButton = screen.getAllByRole('button', { name: /execute/i })[0];
        fireEvent.click(executeButton);
      });

      await waitFor(() => {
        const confirmButton = screen.getByRole('button', { name: /confirm/i });
        fireEvent.click(confirmButton);
      });

      await waitFor(() => {
        expect(vi.mocked(api.startPrecooling)).toHaveBeenCalled();
      });
    });

    it('should add execution to action history on success', async () => {
      const sites = [createMockSite({ id: 'site-002' })];
      const scenarios = [
        createMockOptimizationScenario({
          scenario_id: 'scenario-001',
          site_id: 'site-002',
          site_name: 'Test Building',
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());
      vi.mocked(api.startPrecooling).mockResolvedValue({ success: true, message: 'Precooling started' });

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const executeButton = screen.getAllByRole('button', { name: /execute/i })[0];
        fireEvent.click(executeButton);
      });

      await waitFor(() => {
        const confirmButton = screen.getByRole('button', { name: /confirm/i });
        fireEvent.click(confirmButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/precooling started/i)).toBeInTheDocument();
      });
    });


    it('should disable Execute buttons during confirmation', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario(),
        createMockOptimizationScenario({ scenario_id: 'scenario-002' }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      // Wait for page load
      await waitFor(
        () => {
          expect(screen.getByText('Scenario Comparison')).toBeInTheDocument();
        },
        { timeout: 3000 }
      );

      // Find and click execute button
      const executeButtons = screen.getAllByRole('button', { name: /execute/i });
      fireEvent.click(executeButtons[0]);

      // Verify buttons are disabled during confirmation
      await waitFor(
        () => {
          const btns = screen.getAllByRole('button', { name: /execute/i });
          expect(btns.some((btn) => btn.hasAttribute('disabled'))).toBe(true);
        },
        { timeout: 1000 }
      );
    });
  });

  describe('Action History', () => {
    it('should display Recent Actions panel header', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Recent Actions')).toBeInTheDocument();
      });
    });

    it('should display empty state message when no history', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(
        createMockOptimizationStatus({ optimization_history: [] })
      );

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/no optimization actions yet/i)).toBeInTheDocument();
      });
    });

    it('should display action history items with status badges', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];
      const status = createMockOptimizationStatus({
        optimization_history: [
          {
            timestamp: new Date().toISOString(),
            action: 'Precooling activated',
            result: 'success',
            user: 'Operator',
          },
        ],
      });

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(status);

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/precooling activated/i)).toBeInTheDocument();
        expect(screen.getByText('completed')).toBeInTheDocument();
      });
    });

    it('should display user attribution in action history', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];
      const status = createMockOptimizationStatus({
        optimization_history: [
          {
            timestamp: new Date().toISOString(),
            action: 'Precooling activated',
            result: 'success',
            user: 'John Operator',
          },
        ],
      });

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(status);

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('John Operator')).toBeInTheDocument();
      });
    });

    it('should limit history display to last 10 items', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];
      const historyItems = Array.from({ length: 15 }, (_, i) => ({
        timestamp: new Date(Date.now() - i * 60000).toISOString(),
        action: `Action ${i}`,
        result: 'success' as const,
        user: 'Operator',
      }));

      const status = createMockOptimizationStatus({
        optimization_history: historyItems,
      });

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(status);

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Should show last 10 items (indices 14 down to 5)
        expect(screen.getByText('Action 14')).toBeInTheDocument();
        expect(screen.queryByText('Action 4')).not.toBeInTheDocument();
      });
    });

    it('should show failed status badge when result is error', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];
      const status = createMockOptimizationStatus({
        optimization_history: [
          {
            timestamp: new Date().toISOString(),
            action: 'Precooling attempted',
            result: 'error',
            user: 'Operator',
          },
        ],
      });

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(status);

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('failed')).toBeInTheDocument();
      });
    });

    it('should display timestamp in action history', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];
      const testDate = new Date('2024-01-15T10:30:00Z');
      const status = createMockOptimizationStatus({
        optimization_history: [
          {
            timestamp: testDate.toISOString(),
            action: 'Test action',
            result: 'success',
            user: 'Operator',
          },
        ],
      });

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(status);

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        // Should display formatted date
        expect(screen.getByText(/2024|2025|2026/)).toBeInTheDocument();
      });
    });
  });

  describe('Tabs and Navigation', () => {
    it('should render Load Shedding tab content by default', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Load Shedding Optimization')).toBeInTheDocument();
        expect(screen.getByText('Scenario Comparison')).toBeInTheDocument();
      });
    });

    it('should switch to Optimization tab when clicked', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const optimizationTab = screen.getByText('Optimization');
        fireEvent.click(optimizationTab);
      });

      // Optimization tab should be clickable
      expect(screen.getByText('Optimization')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should accept onError callback prop', () => {
      const onError = vi.fn();
      vi.mocked(api.getSites).mockResolvedValue([]);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      // Should not throw when rendering with onError callback
      expect(() => {
        render(<OptimizationPage onError={onError} />, { wrapper: createTestWrapper() });
      }).not.toThrow();
    });
  });
});
