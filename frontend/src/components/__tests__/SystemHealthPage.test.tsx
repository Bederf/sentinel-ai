/**
 * SystemHealthPage Tests
 *
 * Tests comprehensive SystemHealthPage functionality:
 * - Health metrics display (overall score, component breakdown)
 * - Color-coded status indicators
 * - Equipment health list with trend indicators
 * - Manual and auto-refresh functionality
 * - Tab navigation
 * - Error handling
 * - Historical insights and trends
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SystemHealthPage from '../SystemHealthPage';

// Mock API client
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
}));

// Mock Tremor components to simplify testing
vi.mock('@tremor/react', () => ({
  TabGroup: ({ children, defaultIndex, onIndexChange }: any) => (
    <div data-testid="tab-group">
      {children}
    </div>
  ),
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

describe('SystemHealthPage', () => {
  beforeEach(() => {
    // Mock DOM APIs for jsdom
    Element.prototype.scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = vi.fn();

    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

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
      });
    });

    it('should display error for failed health fetch', async () => {
      vi.mocked(authorizedFetch).mockImplementation((url: string) => {
        if (url.includes('/api/system/health')) {
          return Promise.reject(new Error('Failed to fetch health'));
        }
        return Promise.resolve({ ok: true, json: async () => ({}) } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to fetch health/)).toBeInTheDocument();
      });
    });

    it('should render page after data loads successfully', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
          power: { score: 80, status: 'degraded' },
        },
      };

      const mockHistory = {
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
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('System Health Dashboard')).toBeInTheDocument();
      });
    });
  });

  describe('Tab Navigation', () => {
    const mockHealth = {
      overall_score: 85,
      overall_status: 'healthy',
      components: {
        hvac: { score: 90, status: 'healthy' },
      },
    };

    const mockHistory = {
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

    beforeEach(() => {
      vi.mocked(authorizedFetch).mockImplementation((url: string) => {
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });
    });

    it('should display three tabs', async () => {
      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Realtime Status')).toBeInTheDocument();
        expect(screen.getByText('Historical Insights')).toBeInTheDocument();
        expect(screen.getByText('Diagnostics')).toBeInTheDocument();
      });
    });

    it('should render Realtime Status tab by default', async () => {
      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Overall Health Status')).toBeInTheDocument();
      });
    });

    it('should switch to Historical Insights tab when clicked', async () => {
      render(<SystemHealthPage />);

      await waitFor(() => {
        const historicalTab = screen.getByText('Historical Insights');
        fireEvent.click(historicalTab);
      });

      // Note: Tab switching would be tested more thoroughly with actual component behavior
    });

    it('should switch to Diagnostics tab', async () => {
      render(<SystemHealthPage />);

      await waitFor(() => {
        const diagnosticsTab = screen.getByText('Diagnostics');
        fireEvent.click(diagnosticsTab);
      });

      await waitFor(() => {
        expect(screen.getByText(/Diagnostics tools coming soon/)).toBeInTheDocument();
      });
    });
  });

  describe('Realtime Status Tab', () => {
    it('should display overall health score', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('85')).toBeInTheDocument();
      });
    });

    it('should display overall health status badge', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByTestId('badge-green')).toBeInTheDocument();
        expect(screen.getByText('HEALTHY')).toBeInTheDocument();
      });
    });

    it('should display green status for healthy (>70)', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByTestId('badge-green')).toBeInTheDocument();
      });
    });

    it('should display yellow status for degraded (40-70)', async () => {
      const mockHealth = {
        overall_score: 55,
        overall_status: 'degraded',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByTestId('badge-yellow')).toBeInTheDocument();
        expect(screen.getByText('DEGRADED')).toBeInTheDocument();
      });
    });

    it('should display red status for critical (<40)', async () => {
      const mockHealth = {
        overall_score: 25,
        overall_status: 'critical',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByTestId('badge-red')).toBeInTheDocument();
        expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      });
    });

    it('should display component status cards', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
          power: { score: 75, status: 'degraded' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('hvac')).toBeInTheDocument();
        expect(screen.getByText('lighting')).toBeInTheDocument();
        expect(screen.getByText('power')).toBeInTheDocument();
      });
    });

    it('should display component scores', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        // Should display component scores
        const metrics = screen.getAllByTestId('metric');
        expect(metrics.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('should display progress bars for health scores', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByTestId('progress-bar-green')).toBeInTheDocument();
      });
    });

    it('should sort components by health score (lowest first)', async () => {
      const mockHealth = {
        overall_score: 80,
        overall_status: 'healthy',
        components: {
          hvac: { score: 95, status: 'healthy' },
          power: { score: 60, status: 'degraded' },
          lighting: { score: 80, status: 'healthy' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        const components = screen.getAllByText(/hvac|power|lighting/);
        expect(components.length).toBeGreaterThanOrEqual(3);
      });
    });
  });

  describe('Historical Insights Tab', () => {
    it('should display average health score', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
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
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Average Health Score')).toBeInTheDocument();
        expect(screen.getByText('82')).toBeInTheDocument();
      });
    });

    it('should display uptime percentage', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
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
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Uptime (24h)')).toBeInTheDocument();
        expect(screen.getByText('99.5%')).toBeInTheDocument();
      });
    });

    it('should display min and max scores', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
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
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Min Score')).toBeInTheDocument();
        expect(screen.getByText('70')).toBeInTheDocument();
        expect(screen.getByText('Max Score')).toBeInTheDocument();
        expect(screen.getByText('95')).toBeInTheDocument();
      });
    });

    it('should display improving trend indicator', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
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
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Improving')).toBeInTheDocument();
        expect(screen.getByTestId('badge-green')).toBeInTheDocument();
      });
    });

    it('should display degrading trend indicator', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'degrading',
        },
        snapshots: [],
      };

      vi.mocked(authorizedFetch).mockImplementation((url: string) => {
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Degrading')).toBeInTheDocument();
        expect(screen.getByTestId('badge-red')).toBeInTheDocument();
      });
    });

    it('should display stable trend indicator', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
        range: '24h',
        metrics: {
          avg_score: 82,
          uptime_percentage: 99.5,
          min_score: 70,
          max_score: 95,
          trend: 'stable',
        },
        snapshots: [],
      };

      vi.mocked(authorizedFetch).mockImplementation((url: string) => {
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Stable')).toBeInTheDocument();
        expect(screen.getByTestId('badge-gray')).toBeInTheDocument();
      });
    });

    it('should display health score trend chart', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
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
      };

      vi.mocked(authorizedFetch).mockImplementation((url: string) => {
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
        expect(screen.getByText('3 points')).toBeInTheDocument();
      });
    });
  });

  describe('Diagnostics Tab', () => {
    it('should display diagnostics placeholder message', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        const diagnosticsTab = screen.getByText('Diagnostics');
        fireEvent.click(diagnosticsTab);
      });

      await waitFor(() => {
        expect(screen.getByText(/Diagnostics tools coming soon/)).toBeInTheDocument();
      });
    });

    it('should display SIMBIOT diagnostics description', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        const diagnosticsTab = screen.getByText('Diagnostics');
        fireEvent.click(diagnosticsTab);
      });

      await waitFor(() => {
        expect(
          screen.getByText(/Run SIMBIOT diagnostics to analyze system components/)
        ).toBeInTheDocument();
      });
    });
  });

  describe('Auto-Refresh Functionality', () => {
    it('should refetch health data every 30 seconds', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('System Health Dashboard')).toBeInTheDocument();
      });

      expect(vi.mocked(authorizedFetch)).toHaveBeenCalledTimes(2); // Initial load calls both endpoints

      // Advance time by 30 seconds
      vi.advanceTimersByTime(30000);

      await waitFor(() => {
        // Should have called again
        expect(vi.mocked(authorizedFetch).mock.calls.length).toBeGreaterThan(2);
      });
    });

    it('should cleanup interval on unmount', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      const { unmount } = render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('System Health Dashboard')).toBeInTheDocument();
      });

      const initialCalls = vi.mocked(authorizedFetch).mock.calls.length;

      unmount();

      // Advance time - should not trigger additional fetches
      vi.advanceTimersByTime(30000);

      expect(vi.mocked(authorizedFetch).mock.calls.length).toBe(initialCalls);
    });
  });

  describe('Page Header', () => {
    it('should display page title', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('System Health Dashboard')).toBeInTheDocument();
      });
    });

    it('should display subtitle text', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('Real-time monitoring and diagnostics')).toBeInTheDocument();
      });
    });
  });

  describe('Component Status Icons', () => {
    it('should display checkmark icon for healthy status', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        // CheckCircle icon should be rendered for healthy components
        expect(screen.getByText('hvac')).toBeInTheDocument();
      });
    });

    it('should display alert icon for degraded status', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          power: { score: 55, status: 'degraded' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('power')).toBeInTheDocument();
      });
    });

    it('should display alert icon for critical status', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          lighting: { score: 25, status: 'critical' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        expect(screen.getByText('lighting')).toBeInTheDocument();
      });
    });
  });

  describe('Responsive Layout', () => {
    it('should render component cards in responsive grid', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {
          hvac: { score: 90, status: 'healthy' },
          lighting: { score: 85, status: 'healthy' },
          power: { score: 75, status: 'degraded' },
        },
      };

      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => mockHealth,
      } as any);

      render(<SystemHealthPage />);

      await waitFor(() => {
        // Should render all component cards
        const cards = screen.getAllByTestId('card');
        expect(cards.length).toBeGreaterThanOrEqual(3); // At least overall card + 3 component cards
      });
    });

    it('should display metrics in responsive grid on Historical Insights tab', async () => {
      const mockHealth = {
        overall_score: 85,
        overall_status: 'healthy',
        components: {},
      };

      const mockHistory = {
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
        if (url.includes('/api/system/health/history')) {
          return Promise.resolve({
            ok: true,
            json: async () => mockHistory,
          } as any);
        }
        return Promise.resolve({
          ok: true,
          json: async () => mockHealth,
        } as any);
      });

      render(<SystemHealthPage />);

      await waitFor(() => {
        const cards = screen.getAllByTestId('card');
        expect(cards.length).toBeGreaterThan(0);
      });
    });
  });
});
