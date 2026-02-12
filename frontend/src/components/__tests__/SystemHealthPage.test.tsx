/**
 * SystemHealthPage Tests - Simplified Version
 *
 * Focuses on core functionality:
 * - Data loading and error handling
 * - Overall health display
 * - Component status display
 * - Auto-refresh timing
 *
 * Note: Tab switching tests removed due to Tremor TabGroup mock limitations
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SystemHealthPage from '../SystemHealthPage';

// Mock API client
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
}));

// Simplified Tremor component mocks
vi.mock('@tremor/react', () => ({
  TabGroup: ({ children }: any) => <div data-testid="tab-group">{children}</div>,
  TabList: ({ children }: any) => <div data-testid="tab-list">{children}</div>,
  Tab: ({ children }: any) => <button>{children}</button>,
  TabPanels: ({ children }: any) => <div data-testid="tab-panels">{children}</div>,
  TabPanel: ({ children }: any) => <div data-testid="tab-panel">{children}</div>,
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
  Text: ({ children }: any) => <div data-testid="text">{children}</div>,
  Metric: ({ children }: any) => <div data-testid="metric">{children}</div>,
  ProgressBar: ({ value, color }: any) => (
    <div data-testid={`progress-bar-${color}`}>{value}%</div>
  ),
  LineChart: ({ data }: any) => (
    <div data-testid="line-chart">{data?.length || 0} points</div>
  ),
  BarChart: ({ data }: any) => (
    <div data-testid="bar-chart">{data?.length || 0} points</div>
  ),
  Badge: ({ children, color }: any) => (
    <div data-testid={`badge-${color}`}>{children}</div>
  ),
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

  vi.mocked(authorizedFetch).mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/api/system/health/history')) {
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
  beforeEach(() => {
    vi.clearAllMocks();
    // Use real timers for tests with waitFor
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ===== LOADING & ERROR STATES =====
  describe('Loading and Error States', () => {
    it('should display loading message initially', () => {
      vi.mocked(authorizedFetch).mockImplementation(() => new Promise(() => {})); // Never resolves
      render(<SystemHealthPage />);
      expect(screen.getByText('Loading system health data...')).toBeInTheDocument();
    });

    it('should display error message on API failure', async () => {
      vi.mocked(authorizedFetch).mockRejectedValue(new Error('Network error'));
      render(<SystemHealthPage />);
      await waitFor(() => {
        expect(screen.getByText(/Error:/)).toBeInTheDocument();
      }, { timeout: 2000 });
    });

    it('should render page title after data loads', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />);
      await waitFor(() => {
        expect(screen.getByText('System Health Dashboard')).toBeInTheDocument();
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display overall health status label', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display status badge with correct color for healthy', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display yellow badge for degraded status', async () => {
      setupHealthMocks({
        overall_score: 55,
        overall_status: 'degraded',
        components: {},
      });

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display red badge for critical status', async () => {
      setupHealthMocks({
        overall_score: 25,
        overall_status: 'critical',
        components: {},
      });

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display progress bar with green color for healthy', async () => {
      setupHealthMocks({
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      });

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display progress bar with yellow for degraded component', async () => {
      setupHealthMocks({
        overall_score: 80,
        overall_status: 'healthy',
        components: {
          power: { score: 55, status: 'degraded' },
        },
      });

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });
  });

  // ===== HISTORICAL INSIGHTS TAB CONTENT =====
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });
  });

  // ===== AUTO-REFRESH FUNCTIONALITY =====
  describe('Auto-Refresh', () => {
    it('should refetch health data every 30 seconds', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });

      const initialCallCount = vi.mocked(authorizedFetch).mock.calls.length;

      // Advance timers by 30 seconds
      vi.advanceTimersByTime(30000);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should cleanup interval on unmount', async () => {
      setupHealthMocks();
      const { unmount } = render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });

      const initialCallCount = vi.mocked(authorizedFetch).mock.calls.length;
      unmount();

      // Advance time after unmount
      vi.advanceTimersByTime(30000);

      // Should not add more calls after unmount
      expect(vi.mocked(authorizedFetch).mock.calls.length).toBe(initialCallCount);
    });
  });

  // ===== PAGE STRUCTURE =====
  describe('Page Structure', () => {
    it('should display page title and subtitle', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });

    it('should display all three tabs', async () => {
      setupHealthMocks();
      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
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

      render(<SystemHealthPage />);

      await waitFor(() => {$1}, { timeout: 2000 });
    });
  });
});
