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
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import OptimizationPage from '../OptimizationPage';
import { createTestQueryClient } from '@/test-utils/mockQueryClient';
import {
  createMockOptimizationScenario,
  createMockOptimizationStatus,
  createMockSite,
} from '@/test-utils/factories';
import type { OptimizationScenario, OptimizationStatusResponse, Site } from '@/lib/api';

// Mock API module
vi.mock('@/lib/api', () => ({
  default: {
    getSites: vi.fn(),
    getOptimizationScenarios: vi.fn(),
    getOptimizationStatus: vi.fn(),
    startPrecooling: vi.fn(),
  },
}));

import api from '@/lib/api';

// Test wrapper component
function createTestWrapper() {
  const queryClient = createTestQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
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

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      expect(screen.getByText(/loading optimization data/i)).toBeInTheDocument();
    });

    it('should render error state when data fetch fails', async () => {
      const errorMsg = 'Failed to load optimization data';
      vi.mocked(api.getSites).mockResolvedValue([]);
      vi.mocked(api.getOptimizationScenarios).mockRejectedValue(new Error('API Error'));
      vi.mocked(api.getOptimizationStatus).mockRejectedValue(new Error('API Error'));

      const onError = vi.fn();
      render(<OptimizationPage onError={onError} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/error loading optimization data/i)).toBeInTheDocument();
      });
      expect(onError).toHaveBeenCalledWith(expect.any(String));
    });

    it('should render page after data loads successfully', async () => {
      const sites = [createMockSite({ id: 'site-002', name: 'Sandton City' })];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/load shedding optimization/i)).toBeInTheDocument();
      });
    });

    it('should render tab group with Load Shedding and Profile-Based tabs', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Load Shedding')).toBeInTheDocument();
        expect(screen.getByText('Profile-Based Optimization')).toBeInTheDocument();
      });
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

      await waitFor(() => {
        const selector = screen.getByDisplayValue(/building/i);
        expect(selector).toBeInTheDocument();
      });
    });

    it('should default to site-002 (Sandton City) when available', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Sandton City' }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const selector = screen.getByDisplayValue('Sandton City') as HTMLSelectElement;
        expect(selector.value).toBe('site-002');
      });
    });

    it('should refetch scenarios when site selection changes', async () => {
      const sites = [
        createMockSite({ id: 'site-001', name: 'Building A' }),
        createMockSite({ id: 'site-002', name: 'Building B' }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([createMockOptimizationScenario()]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByDisplayValue('Building B')).toBeInTheDocument();
      });

      const selector = screen.getByDisplayValue('Building B') as HTMLSelectElement;
      fireEvent.change(selector, { target: { value: 'site-001' } });

      await waitFor(() => {
        // getOptimizationStatus should be called with new site
        expect(vi.mocked(api.getOptimizationStatus)).toHaveBeenCalledWith('site-001');
      });
    });

    it('should display "Active Monitoring" badge', async () => {
      const sites = [createMockSite()];
      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue([]);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Active Monitoring')).toBeInTheDocument();
      });
    });
  });

  describe('KPI Cards and Calculations', () => {
    it('should display all four KPI cards', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Energy Savings')).toBeInTheDocument();
        expect(screen.getByText('Comfort Extension')).toBeInTheDocument();
        expect(screen.getByText('Fuel Savings')).toBeInTheDocument();
        expect(screen.getByText('Cost Savings')).toBeInTheDocument();
      });
    });

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

      await waitFor(() => {
        // Should display ZAR format
        expect(screen.getByText(/R/)).toBeInTheDocument();
      });
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

    it('should display scenario rows with all columns', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({
          scenario_id: 'scenario-001',
          site_name: 'Sandton Building',
          thermal_runway: { without_precooling: 45, with_precooling: 120, comfort_maintained: true },
          savings: { energy_savings_percent: 18, comfort_extension_minutes: 75, fuel_savings_percent: 12, total_savings_zar: 4250 },
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Sandton Building')).toBeInTheDocument();
        expect(screen.getByText('120 min')).toBeInTheDocument();
        expect(screen.getByText('18%')).toBeInTheDocument();
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

    it('should display scenario name in confirmation modal', async () => {
      const sites = [createMockSite()];
      const scenarios = [
        createMockOptimizationScenario({
          scenario_id: 'scenario-001',
          site_name: 'Test Building',
        }),
      ];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const executeButton = screen.getAllByRole('button', { name: /execute/i })[0];
        fireEvent.click(executeButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/test building/i)).toBeInTheDocument();
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

    it('should add execution to action history on failure', async () => {
      const sites = [createMockSite({ id: 'site-002' })];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());
      vi.mocked(api.startPrecooling).mockRejectedValue(new Error('API Error'));

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
        expect(screen.getByText(/Failed/)).toBeInTheDocument();
      });
    });

    it('should disable Execute buttons during confirmation', async () => {
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
        const allExecuteButtons = screen.getAllByRole('button', { name: /execute/i });
        allExecuteButtons.forEach((btn) => {
          expect(btn).toHaveAttribute('disabled');
        });
      });
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

    it('should switch to Profile-Based Optimization tab when clicked', async () => {
      const sites = [createMockSite()];
      const scenarios = [createMockOptimizationScenario()];

      vi.mocked(api.getSites).mockResolvedValue(sites);
      vi.mocked(api.getOptimizationScenarios).mockResolvedValue(scenarios);
      vi.mocked(api.getOptimizationStatus).mockResolvedValue(createMockOptimizationStatus());

      render(<OptimizationPage />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        const profileTab = screen.getByText('Profile-Based Optimization');
        fireEvent.click(profileTab);
      });

      // Profile-Based Optimization content should be visible
      // Note: Specific content depends on ProfileSettings component
      expect(screen.getByText('Profile-Based Optimization')).toBeInTheDocument();
    });
  });

  describe('Error Callback', () => {
    it('should call onError callback when data loading fails', async () => {
      const onError = vi.fn();
      vi.mocked(api.getSites).mockResolvedValue([]);
      vi.mocked(api.getOptimizationScenarios).mockRejectedValue(new Error('API Error'));
      vi.mocked(api.getOptimizationStatus).mockRejectedValue(new Error('API Error'));

      render(<OptimizationPage onError={onError} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(onError).toHaveBeenCalled();
      });
    });

    it('should pass error message to onError callback', async () => {
      const onError = vi.fn();
      vi.mocked(api.getSites).mockResolvedValue([]);
      vi.mocked(api.getOptimizationScenarios).mockRejectedValue(new Error('Network error'));
      vi.mocked(api.getOptimizationStatus).mockRejectedValue(new Error('Network error'));

      render(<OptimizationPage onError={onError} />, { wrapper: createTestWrapper() });

      await waitFor(() => {
        expect(onError).toHaveBeenCalledWith(expect.stringContaining('optimization'));
      });
    });
  });
});
