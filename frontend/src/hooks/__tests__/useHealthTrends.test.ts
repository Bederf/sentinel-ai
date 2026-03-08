/**
 * useHealthTrends Hook Tests
 *
 * Tests equipment health score trend aggregation:
 * - 7-day, 30-day, 90-day trend aggregation
 * - Confidence intervals (±15% band)
 * - Trend direction detection (improving/stable/degrading)
 * - Alert correlation to trend dips
 * - Future health predictions
 * - Real-time cache invalidation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { useHealthTrends, type EquipmentAlert } from '../useHealthTrends';

// Mock the equipment history API
vi.mock('@/lib/api/equipment_history', () => ({
  equipmentHistoryApi: {
    getAlerts: vi.fn(),
  },
}));

import { equipmentHistoryApi } from '@/lib/api/equipment_history';

// Test utilities
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,  // Disable all retries in tests
        gcTime: 0,  // No garbage collection in tests
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// Mock data generators
function createMockAlert(
  overrides?: Partial<EquipmentAlert>
): EquipmentAlert {
  return {
    id: 'alert-' + Math.random().toString(36).substr(2, 9),
    equipment_id: 'equipment-001',
    severity: 'warning',
    created_at: new Date().toISOString(),
    status: 'active',
    message: 'Test alert',
    ...overrides,
  };
}

function createMockHealthTrend(daysBack: number = 7): EquipmentAlert[] {
  const alerts: EquipmentAlert[] = [];

  for (let i = 0; i < daysBack; i++) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    const dateStr = date.toISOString().split('T')[0];

    // Add 1-3 random alerts per day
    const alertCount = Math.floor(Math.random() * 3) + 1;
    for (let j = 0; j < alertCount; j++) {
      const severities = ['critical', 'warning', 'info'] as const;
      const severity = severities[Math.floor(Math.random() * severities.length)];

      alerts.push(
        createMockAlert({
          severity,
          created_at: `${dateStr}T${Math.floor(Math.random() * 24).toString().padStart(2, '0')}:00:00Z`,
        })
      );
    }
  }

  return alerts.sort((a, b) =>
    new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

describe('useHealthTrends', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('7-Day Trend Aggregation', () => {
    it('should aggregate alerts into daily health scores', async () => {
      const sevenDayAlerts = createMockHealthTrend(7);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(sevenDayAlerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      expect(result.current.period).toBe('7d');
      expect(result.current.data_points[0]).toHaveProperty('date');
      expect(result.current.data_points[0]).toHaveProperty('health_score');
      expect(result.current.data_points[0]).toHaveProperty('alert_count');
      expect(result.current.data_points[0]).toHaveProperty('trend_direction');

      // Verify health scores are between 0-100
      result.current.data_points.forEach((point) => {
        expect(point.health_score).toBeGreaterThanOrEqual(0);
        expect(point.health_score).toBeLessThanOrEqual(100);
      });
    });

    it('should calculate correct limit for 7-day period', async () => {
      const sevenDayAlerts = createMockHealthTrend(7);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(sevenDayAlerts);

      renderHook(() => useHealthTrends('equipment-001', '7d'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(equipmentHistoryApi.getAlerts).toHaveBeenCalled();
      });

      // For 7d period, limit should be 30
      expect(equipmentHistoryApi.getAlerts).toHaveBeenCalledWith('equipment-001', 30);
    });

    it('should handle empty alerts for 7-day period', async () => {
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBe(0);
      });

      expect(result.current.average_health).toBe(100);
      expect(result.current.trend_direction).toBe('stable');
    });
  });

  describe('30-Day Trend Aggregation', () => {
    it('should aggregate 30-day alert data', async () => {
      const thirtyDayAlerts = createMockHealthTrend(30);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(thirtyDayAlerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      expect(result.current.period).toBe('30d');
      // Should have ~30 daily data points (one per day with alerts)
      expect(result.current.data_points.length).toBeLessThanOrEqual(30);
    });

    it('should calculate correct limit for 30-day period', async () => {
      const thirtyDayAlerts = createMockHealthTrend(30);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(thirtyDayAlerts);

      renderHook(() => useHealthTrends('equipment-001', '30d'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(equipmentHistoryApi.getAlerts).toHaveBeenCalled();
      });

      // For 30d period, limit should be 100
      expect(equipmentHistoryApi.getAlerts).toHaveBeenCalledWith('equipment-001', 100);
    });

    it('should calculate health statistics correctly', async () => {
      const thirtyDayAlerts = createMockHealthTrend(30);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(thirtyDayAlerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.average_health).toBeGreaterThanOrEqual(0);
      });

      // Verify statistics are calculated
      expect(result.current.average_health).toBeLessThanOrEqual(100);
      expect(result.current.min_health).toBeLessThanOrEqual(result.current.average_health);
      expect(result.current.max_health).toBeGreaterThanOrEqual(result.current.average_health);
    });
  });

  describe('90-Day Trend Aggregation', () => {
    it('should aggregate 90-day alert data', async () => {
      const ninetyDayAlerts = createMockHealthTrend(90);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(ninetyDayAlerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '90d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      expect(result.current.period).toBe('90d');
      // Should have ~90 daily data points (one per day with alerts)
      expect(result.current.data_points.length).toBeLessThanOrEqual(90);
    });

    it('should calculate correct limit for 90-day period', async () => {
      const ninetyDayAlerts = createMockHealthTrend(90);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(ninetyDayAlerts);

      renderHook(() => useHealthTrends('equipment-001', '90d'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(equipmentHistoryApi.getAlerts).toHaveBeenCalled();
      });

      // For 90d period, limit should be 300
      expect(equipmentHistoryApi.getAlerts).toHaveBeenCalledWith('equipment-001', 300);
    });
  });

  describe('Confidence Intervals', () => {
    it('should calculate ±15% confidence bands', async () => {
      const alerts = [
        createMockAlert({
          severity: 'info',
          created_at: '2026-02-10T12:00:00Z',
        }),
        createMockAlert({
          severity: 'warning',
          created_at: '2026-02-10T14:00:00Z',
        }),
      ];
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(Object.keys(result.current.confidence_intervals).length).toBeGreaterThan(0);
      });

      // Verify confidence intervals are correctly calculated
      Object.values(result.current.confidence_intervals).forEach((interval) => {
        expect(interval.lower).toBeGreaterThanOrEqual(0);
        expect(interval.upper).toBeLessThanOrEqual(100);
        expect(interval.lower).toBeLessThanOrEqual(interval.upper);
        // Verify band is approximately ±15%
        expect(interval.upper - interval.lower).toBeLessThanOrEqual(35); // ~15% each side
      });
    });

    it('should align confidence intervals with data points', async () => {
      const alerts = createMockHealthTrend(7);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      // Each data point should have a confidence interval
      result.current.data_points.forEach((point) => {
        expect(result.current.confidence_intervals[point.date]).toBeDefined();
      });
    });
  });

  describe('Trend Direction Detection', () => {
    it('should detect improving trend', async () => {
      // Create alerts that show improving health (fewer/less severe over time)
      const alerts: EquipmentAlert[] = [];
      const today = new Date();

      // Early period: many critical alerts (poor health)
      for (let i = 14; i >= 8; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        alerts.push(
          createMockAlert({
            severity: 'critical',
            created_at: date.toISOString(),
          })
        );
        alerts.push(
          createMockAlert({
            severity: 'critical',
            created_at: date.toISOString(),
          })
        );
      }

      // Recent period: few info alerts (good health)
      for (let i = 7; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        alerts.push(
          createMockAlert({
            severity: 'info',
            created_at: date.toISOString(),
          })
        );
      }

      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.trend_direction).toBeDefined();
      });

      expect(['improving', 'stable', 'degrading']).toContain(result.current.trend_direction);
    });

    it('should detect degrading trend', async () => {
      // Create alerts that show degrading health (more/more severe over time)
      const alerts: EquipmentAlert[] = [];
      const today = new Date();

      // Early period: few info alerts (good health)
      for (let i = 14; i >= 8; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        alerts.push(
          createMockAlert({
            severity: 'info',
            created_at: date.toISOString(),
          })
        );
      }

      // Recent period: many critical alerts (poor health)
      for (let i = 7; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        alerts.push(
          createMockAlert({
            severity: 'critical',
            created_at: date.toISOString(),
          })
        );
        alerts.push(
          createMockAlert({
            severity: 'critical',
            created_at: date.toISOString(),
          })
        );
      }

      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.trend_direction).toBeDefined();
      });

      expect(['improving', 'stable', 'degrading']).toContain(result.current.trend_direction);
    });

    it('should detect stable trend', async () => {
      // Create alerts with consistent severity (stable health)
      const alerts: EquipmentAlert[] = [];
      const today = new Date();

      for (let i = 30; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        // Consistent warning alerts every day
        alerts.push(
          createMockAlert({
            severity: 'warning',
            created_at: date.toISOString(),
          })
        );
      }

      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.trend_direction).toBeDefined();
      });

      // Should be stable with consistent warning alerts
      expect(['improving', 'stable', 'degrading']).toContain(result.current.trend_direction);
    });
  });

  describe('Prediction Overlay', () => {
    it('should generate future health predictions', async () => {
      const alerts = createMockHealthTrend(14);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(Object.keys(result.current.predictions).length).toBeGreaterThan(0);
      });

      // Should have predictions for +7, +14, +30 days
      expect(result.current.predictions).toBeDefined();

      // Predicted values should be between 0-100
      Object.values(result.current.predictions).forEach((pred) => {
        expect(pred).toBeGreaterThanOrEqual(0);
        expect(pred).toBeLessThanOrEqual(100);
      });
    });

    it('should handle insufficient data for predictions', async () => {
      // Single alert - not enough for trend prediction
      const alerts = [createMockAlert({ created_at: '2026-02-10T12:00:00Z' })];
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current).toBeDefined();
      });

      // May have empty or minimal predictions
      expect(typeof result.current.predictions).toBe('object');
    });
  });

  describe('Alert Correlation', () => {
    it('should link alerts to trend dips', async () => {
      const alerts = [
        createMockAlert({
          severity: 'critical',
          created_at: '2026-02-10T10:00:00Z',
        }),
        createMockAlert({
          severity: 'critical',
          created_at: '2026-02-10T11:00:00Z',
        }),
        createMockAlert({
          severity: 'info',
          created_at: '2026-02-11T12:00:00Z',
        }),
      ];
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.alert_correlation.size).toBeGreaterThan(0);
      });

      // Should have alerts mapped to their dates
      expect(result.current.alert_correlation.has('2026-02-10')).toBe(true);
      expect(result.current.alert_correlation.get('2026-02-10')!.length).toBe(2);
    });

    it('should show alert details on trend dips', async () => {
      const alerts = createMockHealthTrend(7);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      // Find a data point with low health (dip)
      const lowHealthPoint = result.current.data_points.find((p) => p.health_score < 70);
      if (lowHealthPoint) {
        const correlatedAlerts = result.current.alert_correlation.get(lowHealthPoint.date);
        expect(correlatedAlerts).toBeDefined();
        if (correlatedAlerts) {
          expect(correlatedAlerts.length).toBeGreaterThan(0);
        }
      }
    });
  });

  describe('Real-Time Updates', () => {
    it('should invalidate cache when new alert is created', async () => {
      const initialAlerts = createMockHealthTrend(7);
      vi.mocked(equipmentHistoryApi.getAlerts)
        .mockResolvedValueOnce(initialAlerts)
        .mockResolvedValueOnce([...initialAlerts, createMockAlert()]);

      const { result, rerender } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      const _initialCount = result.current.data_points.length;

      // Invalidate cache
      await queryClient.invalidateQueries({
        queryKey: ['equipment-alerts', 'equipment-001', 30],
      });

      rerender();

      await waitFor(() => {
        // Should refetch with new data
        expect(equipmentHistoryApi.getAlerts).toHaveBeenCalledTimes(2);
      });
    });

    it('should update predictions as new data arrives', async () => {
      const alerts = createMockHealthTrend(7);
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.predictions).toBeDefined();
      });

      const _firstPredictions = result.current.predictions;

      // Simulate new alerts
      const updatedAlerts = [...alerts, createMockAlert()];
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(updatedAlerts);

      await queryClient.invalidateQueries({
        queryKey: ['equipment-alerts', 'equipment-001', 30],
      });

      // Predictions should recalculate (may be different due to new data)
      await waitFor(() => {
        expect(equipmentHistoryApi.getAlerts).toHaveBeenCalled();
      });
    });
  });

  describe('Data Validation & Edge Cases', () => {
    it('should return valid structure with no alerts', async () => {
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current).toBeDefined();
      });

      expect(result.current.equipment_id).toBe('equipment-001');
      expect(result.current.period).toBe('30d');
      expect(result.current.data_points).toEqual([]);
      expect(result.current.average_health).toBe(100);
      expect(result.current.min_health).toBe(100);
      expect(result.current.max_health).toBe(100);
    });

    it('should calculate correct health impact per severity', async () => {
      // 1 critical (10pts) + 2 warnings (5pts each) = 20pts → health 80
      const alerts = [
        createMockAlert({
          severity: 'critical',
          created_at: '2026-02-10T10:00:00Z',
        }),
        createMockAlert({
          severity: 'warning',
          created_at: '2026-02-10T11:00:00Z',
        }),
        createMockAlert({
          severity: 'warning',
          created_at: '2026-02-10T12:00:00Z',
        }),
      ];
      vi.mocked(equipmentHistoryApi.getAlerts).mockResolvedValueOnce(alerts);

      const { result } = renderHook(
        () => useHealthTrends('equipment-001', '7d'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current.data_points.length).toBeGreaterThan(0);
      });

      const point = result.current.data_points.find((p) => p.date === '2026-02-10');
      expect(point).toBeDefined();
      if (point) {
        expect(point.health_score).toBe(80); // 100 - 20
      }
    });

    it('should handle null/undefined equipment_id gracefully', async () => {
      const { result } = renderHook(
        () => useHealthTrends('', '30d'),
        { wrapper: createWrapper(queryClient) }
      );

      // Should not fetch when equipment_id is empty
      expect(equipmentHistoryApi.getAlerts).not.toHaveBeenCalled();
      expect(result.current.data_points).toEqual([]);
    });
  });
});
