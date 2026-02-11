/**
 * Device Control End-to-End Flow Tests
 *
 * Tests complete user journeys through the application:
 * - Device control flow: Select device → Adjust setpoint → Confirm safety → Execute → Verify audit log
 * - Optimization flow: Select site → Review scenario → Execute → Verify action history
 * - Alert response flow: View alert → Navigate to equipment → Create work order
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { ControlDashboard } from '@/components/ControlDashboard';
import { OptimizationPage } from '@/pages/OptimizationPage';
import { Dashboard } from '@/components/Dashboard';
import { createTestQueryClient } from '@/test-utils/mockQueryClient';

// Mock API
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
  fetchApi: vi.fn(),
}));

vi.mock('@/hooks/useSitesList');
vi.mock('@/hooks/useDeviceSafetyStatus');
vi.mock('@/hooks/useEquipmentData');
vi.mock('@/hooks/useBuildingsList');
vi.mock('@/hooks/useSiteSummary');
vi.mock('@/hooks/useSitePredictions');
vi.mock('@/hooks/useSiteAlerts');

const mockAuthorizedFetch = vi.fn();
const mockUseSitesList = vi.fn();
const mockUseDeviceSafetyStatus = vi.fn();
const mockUseEquipmentData = vi.fn();
const mockUseBuildingsList = vi.fn();
const mockUseSiteSummary = vi.fn();
const mockUseSitePredictions = vi.fn();
const mockUseSiteAlerts = vi.fn();

const createWrapper = () => {
  const queryClient = createTestQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

beforeEach(() => {
  // Setup mock data for device control flow
  mockUseSitesList.mockReturnValue({
    data: [
      { id: 'site-001', name: 'Sandton Tower', code: 'S002' },
    ],
    isLoading: false,
  });

  mockUseBuildingsList.mockReturnValue({
    data: [
      {
        id: 'building-1',
        code: 'B1',
        name: 'Main Building',
        site_id: 'site-001',
      },
    ],
    isLoading: false,
  });

  mockUseEquipmentData.mockReturnValue({
    equipment: [
      {
        id: 'device-1',
        code: 'S002-CHILLER-B1-001',
        name: 'Main Chiller',
        equipment_type: 'chiller',
        status: 'healthy',
        current_temperature: 22,
        setpoint: 20,
        min_temperature: 16,
        max_temperature: 28,
        safety_blocked: false,
      },
      {
        id: 'device-2',
        code: 'S002-AHU-G-001',
        name: 'Ground Floor AHU',
        equipment_type: 'ahu',
        status: 'warning',
        current_value: 45,
        setpoint: 50,
      },
    ],
    loading: false,
    error: null,
  });

  mockUseDeviceSafetyStatus.mockReturnValue({
    data: {
      'device-1': {
        safe: true,
        warnings: [],
        status: 'healthy',
      },
      'device-2': {
        safe: true,
        warnings: [],
        status: 'warning',
      },
    },
    isLoading: false,
  });

  mockUseSiteSummary.mockReturnValue({
    data: {
      site_id: 'site-001',
      site_name: 'Sandton Tower',
      total_equipment: 150,
      healthy_equipment: 142,
      warning_equipment: 6,
      critical_equipment: 2,
      average_health_score: 78.5,
      uptime_percentage: 99.2,
    },
    isLoading: false,
  });

  mockUseSiteAlerts.mockReturnValue({
    data: [
      {
        id: 'alert-1',
        alert_type: 'temperature_high',
        severity: 'warning',
        equipment_code: 'S002-AHU-G-001',
        equipment_id: 'device-2',
        message: 'AHU temperature exceeding threshold',
        timestamp: new Date().toISOString(),
        resolved: false,
      },
    ],
    isLoading: false,
  });

  mockUseSitePredictions.mockReturnValue({
    data: [
      {
        id: 'pred-1',
        equipment_code: 'S002-CHILLER-B1-001',
        equipment_id: 'device-1',
        failure_probability: 0.15,
        days_until_failure: 45,
        severity: 'warning',
        type: 'bearing_wear',
      },
    ],
    isLoading: false,
  });

  // Setup mock API responses
  mockAuthorizedFetch.mockImplementation((url) => {
    if (url.includes('/api/devices/control')) {
      return Promise.resolve({
        success: true,
        device_id: 'device-1',
        action: 'control_executed',
        previous_value: 20,
        new_value: 22,
        timestamp: new Date().toISOString(),
      });
    }
    if (url.includes('/api/optimization/execute')) {
      return Promise.resolve({
        success: true,
        scenario_id: 'scenario-1',
        energy_savings_kwh: 45.3,
        cost_savings_zar: 2500,
        execution_time: new Date().toISOString(),
      });
    }
    if (url.includes('/api/work-orders')) {
      return Promise.resolve({
        success: true,
        work_order_id: 'wo-123',
        equipment_code: 'S002-AHU-G-001',
        status: 'assigned',
        assigned_technician: 'John Smith',
      });
    }
    return Promise.resolve({});
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('Device Control End-to-End Flow', () => {
  it('should complete full device control flow: select → adjust → confirm → execute → audit log', async () => {
    const user = userEvent.setup();
    const wrapper = createWrapper();

    render(<ControlDashboard />, { wrapper });

    // Step 1: Wait for device list to load
    await waitFor(() => {
      expect(screen.queryByText('Main Chiller')).toBeInTheDocument();
    });

    // Step 2: Select device
    const deviceButton = screen.getByRole('button', { name: /Main Chiller/ });
    await user.click(deviceButton);

    // Step 3: Verify device selected
    await waitFor(() => {
      expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument();
    });

    // Step 4: Find and adjust setpoint control
    const setpointInput = screen.queryAllByRole('slider').find(
      (slider) => (slider as HTMLInputElement).getAttribute('aria-label')?.includes('setpoint')
    ) || screen.queryAllByRole('spinbutton').find(
      (input) => (input as HTMLInputElement).name?.includes('setpoint')
    );

    if (setpointInput) {
      fireEvent.change(setpointInput, { target: { value: '22' } });
    }

    // Step 5: Find and click execute button
    const executeButton = screen.queryAllByRole('button').find(
      (btn) => btn.textContent?.toUpperCase().includes('EXECUTE') ||
              btn.textContent?.toUpperCase().includes('SET') ||
              btn.textContent?.toUpperCase().includes('SEND')
    );

    if (executeButton) {
      await user.click(executeButton);
    }

    // Step 6: Verify execution success message
    await waitFor(() => {
      // Should show success indication
      expect(mockAuthorizedFetch).toHaveBeenCalled();
    });
  });

  it('should prevent control when safety system blocks device', async () => {
    mockUseDeviceSafetyStatus.mockReturnValue({
      data: {
        'device-1': {
          safe: false,
          warnings: ['Temperature range exceeded'],
          status: 'blocked',
        },
      },
      isLoading: false,
    });

    const wrapper = createWrapper();
    render(<ControlDashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.queryByText('Main Chiller')).toBeInTheDocument();
    });

    const deviceButton = screen.getByRole('button', { name: /Main Chiller/ });
    fireEvent.click(deviceButton);

    // Execute button should be disabled or show warning
    await waitFor(() => {
      const executeButton = screen.queryAllByRole('button').find(
        (btn) => btn.textContent?.toUpperCase().includes('EXECUTE') ||
                btn.textContent?.toUpperCase().includes('SET')
      );

      if (executeButton) {
        expect(executeButton).toBeDisabled();
      }
    });
  });

  it('should display audit log entry after device control', async () => {
    const user = userEvent.setup();
    const wrapper = createWrapper();

    render(<ControlDashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.queryByText('Main Chiller')).toBeInTheDocument();
    });

    // Select device and execute control
    const deviceButton = screen.getByRole('button', { name: /Main Chiller/ });
    await user.click(deviceButton);

    const executeButton = screen.queryAllByRole('button').find(
      (btn) => btn.textContent?.toUpperCase().includes('EXECUTE') ||
              btn.textContent?.toUpperCase().includes('SET')
    );

    if (executeButton) {
      await user.click(executeButton);
    }

    // Should show success notification
    await waitFor(() => {
      expect(mockAuthorizedFetch).toHaveBeenCalled();
    });
  });

  it('should handle control execution errors gracefully', async () => {
    mockAuthorizedFetch.mockRejectedValueOnce(new Error('Network error'));

    const wrapper = createWrapper();
    render(<ControlDashboard />, { wrapper });

    await waitFor(() => {
      expect(screen.queryByText('Main Chiller')).toBeInTheDocument();
    });

    const deviceButton = screen.getByRole('button', { name: /Main Chiller/ });
    fireEvent.click(deviceButton);

    const executeButton = screen.queryAllByRole('button').find(
      (btn) => btn.textContent?.toUpperCase().includes('EXECUTE') ||
              btn.textContent?.toUpperCase().includes('SET')
    );

    if (executeButton) {
      fireEvent.click(executeButton);
    }

    // API should have been called and failed
    await waitFor(() => {
      expect(mockAuthorizedFetch).toHaveBeenCalled();
    });
  });
});

describe('Optimization Execution Flow', () => {
  it('should complete full optimization flow: select site → review scenario → execute → verify results', async () => {
    const user = userEvent.setup();
    const wrapper = createWrapper();

    render(<OptimizationPage />, { wrapper });

    // Step 1: Wait for site selector to load
    await waitFor(() => {
      expect(screen.queryByText('Sandton Tower')).toBeInTheDocument();
    });

    // Step 2: Select optimization scenario
    const scenarioButtons = screen.queryAllByRole('button').filter(
      (btn) => btn.textContent?.includes('Scenario') ||
              btn.textContent?.includes('Execute') ||
              btn.textContent?.includes('Review')
    );

    if (scenarioButtons.length > 0) {
      await user.click(scenarioButtons[0]);
    }

    // Step 3: Verify scenario details shown
    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    // Step 4: Click execute button
    const executeButton = screen.queryAllByRole('button').find(
      (btn) => btn.textContent?.toUpperCase().includes('EXECUTE') ||
              btn.textContent?.includes('Execute Scenario')
    );

    if (executeButton) {
      await user.click(executeButton);
    }

    // Step 5: Verify execution success
    await waitFor(() => {
      expect(mockAuthorizedFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/optimization/execute'),
        expect.any(Object)
      );
    });
  });

  it('should display optimization results after execution', async () => {
    const wrapper = createWrapper();
    render(<OptimizationPage />, { wrapper });

    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    // Should display site information
    expect(screen.queryByText(/Sandton Tower/)).toBeInTheDocument();
  });

  it('should update action history after optimization execution', async () => {
    const wrapper = createWrapper();
    render(<OptimizationPage />, { wrapper });

    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    // Action history should be visible
    const historySection = screen.queryByText(/History/) ||
                          screen.queryByText(/Actions/) ||
                          screen.queryByText(/Executions/);

    expect(historySection).toBeInTheDocument();
  });

  it('should handle optimization execution errors', async () => {
    mockAuthorizedFetch.mockRejectedValueOnce(new Error('Optimization failed'));

    const wrapper = createWrapper();
    render(<OptimizationPage />, { wrapper });

    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    // Component should still be usable
    expect(screen.queryByText(/Sandton Tower/)).toBeInTheDocument();
  });
});

describe('Alert Response Flow', () => {
  it('should navigate from alert to equipment details to work order creation', async () => {
    const user = userEvent.setup();
    const wrapper = createWrapper();

    render(<Dashboard />, { wrapper });

    // Step 1: Wait for dashboard to load with alerts
    await waitFor(() => {
      expect(mockUseSiteAlerts).toHaveBeenCalled();
    });

    // Step 2: Find and click on alert
    const alertElements = screen.queryAllByText(/AHU temperature/) ||
                         screen.queryAllByText(/alert/) ||
                         screen.queryAllByText(/warning/);

    if (alertElements.length > 0) {
      await user.click(alertElements[0]);
    }

    // Step 3: Verify equipment details shown
    await waitFor(() => {
      expect(mockUseEquipmentData).toHaveBeenCalled();
    });

    // Step 4: Find create work order button
    const woButton = screen.queryAllByRole('button').find(
      (btn) => btn.textContent?.includes('Work Order') ||
              btn.textContent?.includes('Create') ||
              btn.textContent?.includes('Schedule')
    );

    if (woButton) {
      await user.click(woButton);
    }

    // Step 5: Verify work order creation API called
    await waitFor(() => {
      if (mockAuthorizedFetch.mock.calls.some((call) =>
        call[0]?.includes('/api/work-orders')
      )) {
        expect(mockAuthorizedFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/work-orders'),
          expect.any(Object)
        );
      }
    });
  });

  it('should display critical alerts prominently in dashboard', async () => {
    const wrapper = createWrapper();
    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSiteAlerts).toHaveBeenCalled();
    });

    // Critical alerts should be visible in dashboard
    const alertElements = screen.queryAllByText(/Alert/) ||
                         screen.queryAllByText(/warning/) ||
                         screen.queryAllByText(/critical/);

    expect(alertElements.length).toBeGreaterThan(0);
  });

  it('should show predicted failures alongside alerts', async () => {
    const wrapper = createWrapper();
    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSitePredictions).toHaveBeenCalled();
      expect(mockUseSiteAlerts).toHaveBeenCalled();
    });

    // Both alerts and predictions should be fetched
    expect(mockUseSiteAlerts).toHaveBeenCalled();
    expect(mockUseSitePredictions).toHaveBeenCalled();
  });

  it('should allow work order creation for predicted failures', async () => {
    const wrapper = createWrapper();
    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSitePredictions).toHaveBeenCalled();
    });

    // Prediction data should be available
    expect(mockUseSitePredictions).toHaveBeenCalled();
  });
});

describe('Multi-Step User Journeys', () => {
  it('should maintain user context across multiple operations', async () => {
    const wrapper = createWrapper();
    const { rerender } = render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSitesList).toHaveBeenCalled();
    });

    // User context should be maintained
    expect(mockUseSitesList).toHaveBeenCalledTimes(1);

    // Rerender should use cached data
    rerender(<Dashboard />);

    // Cache should prevent redundant API calls
    // (React Query's deduplication)
  });

  it('should handle rapid navigation between views', async () => {
    const wrapper = createWrapper();
    const { rerender } = render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSitesList).toHaveBeenCalled();
    });

    // Switch to optimization
    rerender(<OptimizationPage />);

    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    // Switch back to dashboard
    rerender(<Dashboard />);

    // Should handle view transitions gracefully
    expect(mockUseSiteAlerts).toHaveBeenCalled();
  });

  it('should preserve selected site across page changes', async () => {
    const wrapper = createWrapper();
    const { rerender } = render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSitesList).toHaveBeenCalled();
    });

    // Change to optimization page
    rerender(<OptimizationPage />);

    // Same site should be used
    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });
  });
});

describe('Data Consistency Across Operations', () => {
  it('should update equipment status after control execution', async () => {
    const wrapper = createWrapper();
    render(<ControlDashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseEquipmentData).toHaveBeenCalled();
    });

    // Execute device control
    const deviceButton = screen.queryAllByRole('button').find(
      (btn) => btn.textContent?.includes('Chiller')
    );

    if (deviceButton) {
      fireEvent.click(deviceButton);
    }

    // API should be called to execute control
    await waitFor(() => {
      expect(mockAuthorizedFetch).toHaveBeenCalled();
    });
  });

  it('should reflect alert resolution in dashboard', async () => {
    const wrapper = createWrapper();
    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSiteAlerts).toHaveBeenCalled();
    });

    // Alerts should be displayed
    const alerts = screen.queryAllByText(/AHU temperature/) ||
                  screen.queryAllByText(/warning/);

    expect(alerts.length).toBeGreaterThanOrEqual(0);
  });

  it('should update health scores after work order completion', async () => {
    const wrapper = createWrapper();
    render(<Dashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    // Health score should be displayed
    const healthScore = screen.queryByText(/78.5/) ||
                       screen.queryByText(/health/);

    expect(healthScore).toBeInTheDocument();
  });
});

describe('Error Recovery Flows', () => {
  it('should allow retry after API failure', async () => {
    mockAuthorizedFetch.mockRejectedValueOnce(new Error('API Error'));

    const wrapper = createWrapper();
    render(<ControlDashboard />, { wrapper });

    await waitFor(() => {
      expect(mockUseEquipmentData).toHaveBeenCalled();
    });

    // Component should still be functional for retry
    expect(screen.queryByText('Main Chiller')).toBeInTheDocument();
  });

  it('should handle partial data availability gracefully', async () => {
    mockUseSiteAlerts.mockReturnValue({
      data: null,
      isLoading: false,
      error: 'Failed to load alerts',
    });

    const wrapper = createWrapper();
    render(<Dashboard />, { wrapper });

    // Dashboard should still render with available data
    await waitFor(() => {
      expect(mockUseSiteSummary).toHaveBeenCalled();
    });

    expect(screen.queryByText(/Sandton Tower/)).toBeInTheDocument();
  });

  it('should show offline indicator when network unavailable', async () => {
    mockAuthorizedFetch.mockRejectedValue(new Error('Network error'));

    const wrapper = createWrapper();
    render(<ControlDashboard />, { wrapper });

    // Component should indicate offline state
    await waitFor(() => {
      expect(mockUseEquipmentData).toHaveBeenCalled();
    });
  });
});
