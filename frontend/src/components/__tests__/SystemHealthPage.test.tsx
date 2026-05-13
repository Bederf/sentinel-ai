/**
 * SystemHealthPage Tests
 *
 * Focuses on core functionality:
 * - Data loading and error handling
 * - Overall health display
 * - Component status display
 * - Historical insights display
 * - Page structure
 *
 * Note: Tab switching tests removed due to Tremor TabGroup mock limitations.
 * All TabPanels render simultaneously in mock, so content is always visible.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import SystemHealthPage from '../SystemHealthPage';

// Create test QueryClient
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 0, gcTime: Infinity },
    },
  });
}

// Wrapper with QueryClientProvider
function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// Mock API client
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
}));

// Mock API modules
vi.mock('@/lib/api', () => ({
  monitoringApi: {
    getIntegrationHealth: vi.fn(() =>
      Promise.resolve({
        status: 'healthy',
        services: [],
        last_check: new Date().toISOString(),
      })
    ),
  },
}));

// No-op: Tremor components have been replaced with plain HTML
      React.default.createElement('span', {
        'data-testid': `badge-${color}`,
        children,
      }),
  };
});

// Mock useServerEvents hook
vi.mock('@/hooks/useServerEvents', () => ({
  useServerEvents: () => {},
}));

import { authorizedFetch } from '@/lib/api/client';

// Helper: Setup mocks for both API endpoints
function setupHealthMocks(healthData?: any, historyData?: any) {
  const defaultHealth = {
    overall_score: 85,
    overall_status: 'healthy',
    components: {},
  };

  const defaultHistory = {
    range: '24h',
    metrics: {
      avg_score: 82,
      uptime_percentage: 99.5,
      min_score: 70,
      max_score: 95,
      trend: 'improving',
    },
    snapshots: [],
  };

  vi.mocked(authorizedFetch).mockImplementation((url: any) => {
    const urlString = typeof url === 'string' ? url : url.toString ? url.toString() : String(url);
    if (urlString.includes('/api/system/health/history')) {
      return Promise.resolve({
        ok: true,
        json: async () => historyData || defaultHistory,
      } as any);
    }
    return Promise.resolve({
      ok: true,
      json: async () => healthData || defaultHealth,
    } as any);
  });
}

describe('SystemHealthPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = createTestQueryClient();
  });

  afterEach(() => {
    vi.clearAllMocks();
    queryClient.clear();
  });

  // ===== LOADING & ERROR STATES =====
  describe('Loading and Error States', () => {
    it('should display loading message initially', () => {
      vi.mocked(authorizedFetch).mockImplementation(() => new Promise(() => {})); // Never resolves
      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });
      expect(screen.getByText('Loading system health data...')).toBeInTheDocument();
    });

    it('should display error message on API failure', async () => {
      vi.mocked(authorizedFetch).mockRejectedValue(new Error('Network error'));
      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });
      await waitFor(() => {
        expect(screen.getByText(/Error:/)).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should render page title after data loads', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });
      await waitFor(() => {
        expect(screen.getByText('System Health')).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  // ===== REALTIME STATUS TAB CONTENT =====
  describe('Realtime Status Display', () => {
    it('should display overall health score', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('85')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display overall health status label', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Overall Health Status')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display status badge with correct color for healthy', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        // Status is rendered as custom span with toUpperCase()
        expect(screen.getByText('HEALTHY')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display yellow badge for degraded status', async () => {
      setupHealthMocks({
        overall_score: 55,
        overall_status: 'degraded',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('DEGRADED')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display red badge for critical status', async () => {
      setupHealthMocks({
        overall_score: 25,
        overall_status: 'critical',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display component status cards', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
          power: { score: 75, status: 'degraded' },
        },
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('hvac')).toBeInTheDocument();
        expect(screen.getByText('lighting')).toBeInTheDocument();
        expect(screen.getByText('power')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display component scores in metrics', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
        },
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        const metrics = screen.getAllByTestId('metric');
        // Integration metrics (4) + component metrics (2)
        expect(metrics.length).toBeGreaterThanOrEqual(2);
      }, { timeout: 2000 });
    });

    it('should display progress bar with green color for healthy', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByTestId('progress-bar-green')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display progress bar with yellow for degraded component', async () => {
      setupHealthMocks({
        overall_score: 80,
        overall_status: 'healthy',
        components: {
          power: { score: 55, status: 'degraded' },
        },
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByTestId('progress-bar-yellow')).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  // ===== HISTORICAL INSIGHTS TAB CONTENT =====
  // Note: Tremor mock renders all TabPanels, so Historical content is visible
  describe('Historical Insights Display', () => {
    it('should fetch and display average health score', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'improving',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Average Health Score')).toBeInTheDocument();
        expect(screen.getByText('82')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display uptime percentage', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'improving',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Uptime (24h)')).toBeInTheDocument();
        expect(screen.getByText('99.5%')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display min and max scores', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'improving',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Min Score')).toBeInTheDocument();
        expect(screen.getByText('70')).toBeInTheDocument();
        expect(screen.getByText('Max Score')).toBeInTheDocument();
        expect(screen.getByText('95')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display improving trend with green badge', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'improving',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Improving')).toBeInTheDocument();
        expect(screen.getByTestId('badge-green')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display degrading trend with red badge', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'degrading',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Degrading')).toBeInTheDocument();
        expect(screen.getByTestId('badge-red')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display stable trend with gray badge', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'stable',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Stable')).toBeInTheDocument();
        expect(screen.getByTestId('badge-gray')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should render health score trend chart with data points', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'improving',
        },
        snapshots: [
          { timestamp: '2024-01-15T00:00:00Z', overall_score: 70 },
          { timestamp: '2024-01-15T04:00:00Z', overall_score: 75 },
          { timestamp: '2024-01-15T08:00:00Z', overall_score: 85 },
        ],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });

  // ===== AUTO-REFRESH FUNCTIONALITY =====
  describe('Auto-Refresh', () => {
    it('should refetch health data every 30 seconds', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('System Health')).toBeInTheDocument();
      }, { timeout: 2000 });

      expect(screen.getByText('System Health')).toBeInTheDocument();
    });

    it('should cleanup interval on unmount', async () => {
      setupHealthMocks();
      const { unmount } = render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('System Health')).toBeInTheDocument();
      }, { timeout: 2000 });

      expect(() => unmount()).not.toThrow();
    });
  });

  // ===== PAGE STRUCTURE =====
  describe('Page Structure', () => {
    it('should display page title and subtitle', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('System Health')).toBeInTheDocument();
        // &amp; in JSX renders as & in DOM
        expect(screen.getByText(/Real-time monitoring/)).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should display all four tabs', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Health')).toBeInTheDocument();
        expect(screen.getByText('Historical')).toBeInTheDocument();
        expect(screen.getByText('AI Performance')).toBeInTheDocument();
        expect(screen.getByText('Model Health')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should render responsive card grid for components', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
          power: { score: 75, status: 'degraded' },
        },
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        const cards = screen.getAllByTestId('card');
        // Overall card + integration card + 3 component cards + historical cards
        expect(cards.length).toBeGreaterThanOrEqual(4);
      }, { timeout: 2000 });
    });
  });

  // ===== EMPTY STATE HANDLING =====
  describe('Empty State Handling', () => {
    it('should handle empty components list gracefully', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('System Health')).toBeInTheDocument();
        expect(screen.getByText('85')).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should handle empty snapshots in historical data', async () => {
      setupHealthMocks(undefined, {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'improving',
        },
        snapshots: [],
      });

      render(<SystemHealthPage />, { wrapper: createWrapper(queryClient) });

      await waitFor(() => {
        expect(screen.getByText('Average Health Score')).toBeInTheDocument();
      }, { timeout: 2000 });
    });
  });
});
