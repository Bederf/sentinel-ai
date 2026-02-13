/**
 * React Query hook for equipment health score trends
 *
 * Aggregates equipment health data over time periods (7-day, 30-day, 90-day)
 * and calculates trend direction with confidence intervals.
 *
 * Useful for: Dashboard risk scoring, trend visualization, predictive analysis
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { equipmentHistoryApi, type EquipmentAlert } from '@/lib/api/equipment_history';

/**
 * Daily aggregated health data point
 */
export interface HealthTrendDataPoint {
  date: string; // ISO date string
  health_score: number; // 0-100
  alert_count: number; // Number of alerts on this date
  trend_direction: 'improving' | 'stable' | 'degrading';
}

/**
 * Confidence interval for health score predictions
 */
export interface ConfidenceInterval {
  lower: number; // Lower bound (model uncertainty)
  upper: number; // Upper bound
}

/**
 * Health trend analysis result
 */
export interface HealthTrend {
  equipment_id: string;
  period: '7d' | '30d' | '90d';
  data_points: HealthTrendDataPoint[];
  average_health: number;
  min_health: number;
  max_health: number;
  trend_direction: 'improving' | 'stable' | 'degrading';
  confidence_intervals: Record<string, ConfidenceInterval>; // date → interval
  predictions: Record<string, number>; // date (+7d, +14d, +30d) → predicted health
  alert_correlation: Map<string, EquipmentAlert[]>; // date → alerts on that date
  last_updated: string;
}

/**
 * Aggregate alerts into daily health scores
 *
 * Algorithm:
 * 1. Group alerts by date
 * 2. Calculate health score for each date (100 - (critical*10 + warning*5 + info*1))
 * 3. Identify trend direction (comparing moving averages)
 * 4. Calculate confidence intervals (±15% band around trend)
 * 5. Link alerts to trend dips
 *
 * @param alerts Raw equipment alerts
 * @param period Aggregation period ('7d', '30d', '90d')
 * @returns Aggregated daily health trend data
 */
function aggregateAlertsToTrend(
  alerts: EquipmentAlert[],
  period: '7d' | '30d' | '90d'
): HealthTrendDataPoint[] {
  if (!alerts || alerts.length === 0) {
    return [];
  }

  // Group alerts by date
  const alertsByDate = new Map<string, EquipmentAlert[]>();
  alerts.forEach((alert) => {
    const date = new Date(alert.created_at).toISOString().split('T')[0];
    if (!alertsByDate.has(date)) {
      alertsByDate.set(date, []);
    }
    alertsByDate.get(date)!.push(alert);
  });

  // Calculate health score for each date
  const trend: HealthTrendDataPoint[] = Array.from(alertsByDate.entries()).map(
    ([date, dateAlerts]) => {
      // Calculate severity impact
      let severityScore = 0;
      dateAlerts.forEach((alert) => {
        if (alert.severity === 'critical') severityScore += 10;
        else if (alert.severity === 'warning') severityScore += 5;
        else severityScore += 1; // info
      });

      const health_score = Math.max(0, 100 - severityScore);

      // Determine trend direction based on severity
      let trend_direction: 'improving' | 'stable' | 'degrading' = 'stable';
      if (severityScore > 15) trend_direction = 'degrading';
      else if (severityScore < 5) trend_direction = 'improving';

      return {
        date,
        health_score,
        alert_count: dateAlerts.length,
        trend_direction,
      };
    }
  );

  // Sort by date
  return trend.sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Calculate confidence intervals (±15% band around health score)
 */
function calculateConfidenceIntervals(
  trend: HealthTrendDataPoint[]
): Record<string, ConfidenceInterval> {
  const intervals: Record<string, ConfidenceInterval> = {};

  trend.forEach((point) => {
    const margin = point.health_score * 0.15; // ±15% band
    intervals[point.date] = {
      lower: Math.max(0, point.health_score - margin),
      upper: Math.min(100, point.health_score + margin),
    };
  });

  return intervals;
}

/**
 * Predict future health scores based on trend
 * Simple linear extrapolation from recent points
 */
function predictFutureHealth(trend: HealthTrendDataPoint[]): Record<string, number> {
  const predictions: Record<string, number> = {};

  if (trend.length < 2) {
    // Not enough data to predict
    return predictions;
  }

  // Calculate simple linear trend
  const recentPoints = trend.slice(-7); // Last 7 data points
  let healthDelta = 0;
  if (recentPoints.length >= 2) {
    healthDelta =
      (recentPoints[recentPoints.length - 1].health_score - recentPoints[0].health_score) /
      (recentPoints.length - 1);
  }

  const lastHealth = trend[trend.length - 1].health_score;
  const lastDate = new Date(trend[trend.length - 1].date);

  // Predict for +7, +14, +30 days
  const daysToPredict = [7, 14, 30];
  daysToPredict.forEach((days) => {
    const futureDate = new Date(lastDate);
    futureDate.setDate(futureDate.getDate() + days);
    const predictedHealth = Math.max(0, Math.min(100, lastHealth + healthDelta * days));
    predictions[futureDate.toISOString().split('T')[0]] = predictedHealth;
  });

  return predictions;
}

/**
 * Determine overall trend direction from data
 */
function determineTrendDirection(trend: HealthTrendDataPoint[]): 'improving' | 'stable' | 'degrading' {
  if (trend.length < 2) return 'stable';

  const firstHalf = trend.slice(0, Math.ceil(trend.length / 2)).map((p) => p.health_score);
  const secondHalf = trend.slice(Math.ceil(trend.length / 2)).map((p) => p.health_score);

  const firstAvg = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
  const secondAvg = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;

  if (secondAvg > firstAvg + 5) return 'improving';
  if (secondAvg < firstAvg - 5) return 'degrading';
  return 'stable';
}

/**
 * Create alert correlation map from trend data
 */
function createAlertCorrelationMap(
  data_points: HealthTrendDataPoint[],
  alerts: EquipmentAlert[]
): Map<string, EquipmentAlert[]> {
  const alert_correlation = new Map<string, EquipmentAlert[]>();
  data_points.forEach((point) => {
    const dateAlerts = alerts.filter(
      (alert) => new Date(alert.created_at).toISOString().split('T')[0] === point.date
    );
    if (dateAlerts.length > 0) {
      alert_correlation.set(point.date, dateAlerts);
    }
  });
  return alert_correlation;
}

/**
 * Build trend result from aggregated data
 */
function buildTrendResult(
  equipmentId: string,
  period: '7d' | '30d' | '90d',
  data_points: HealthTrendDataPoint[],
  alerts: EquipmentAlert[]
): HealthTrend {
  if (data_points.length === 0) {
    return {
      equipment_id: equipmentId,
      period,
      data_points: [],
      average_health: 100,
      min_health: 100,
      max_health: 100,
      trend_direction: 'stable',
      confidence_intervals: {},
      predictions: {},
      alert_correlation: new Map(),
      last_updated: new Date().toISOString(),
    };
  }

  const health_scores = data_points.map((p) => p.health_score);
  const average_health = health_scores.reduce((a, b) => a + b, 0) / health_scores.length;
  const min_health = Math.min(...health_scores);
  const max_health = Math.max(...health_scores);

  return {
    equipment_id: equipmentId,
    period,
    data_points,
    average_health,
    min_health,
    max_health,
    trend_direction: determineTrendDirection(data_points),
    confidence_intervals: calculateConfidenceIntervals(data_points),
    predictions: predictFutureHealth(data_points),
    alert_correlation: createAlertCorrelationMap(data_points, alerts),
    last_updated: new Date().toISOString(),
  };
}

/**
 * Fetch and analyze health trends for equipment
 *
 * @param equipmentId Equipment UUID
 * @param period Trend period ('7d', '30d', '90d')
 * @returns Health trend analysis with predictions and correlations
 *
 * @example
 * const { data: trend } = useHealthTrends(equipmentId, '30d');
 * // trend = { data_points: [...], average_health: 72, trend_direction: 'improving', ... }
 */
export function useHealthTrends(
  equipmentId: string,
  period: '7d' | '30d' | '90d' = '30d'
) {
  // Determine limit based on period
  const limitMap = { '7d': 30, '30d': 100, '90d': 300 };
  const limit = limitMap[period];

  const { data: alerts = [] } = useQuery({
    queryKey: ['equipment-alerts', equipmentId, limit],
    queryFn: () => equipmentHistoryApi.getAlerts(equipmentId, limit),
    staleTime: 60000, // 1 minute
    gcTime: 5 * 60 * 1000, // 5 minutes
    enabled: !!equipmentId,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });

  // Aggregate and analyze trends
  return useMemo(
    () => buildTrendResult(equipmentId, period, aggregateAlertsToTrend(alerts, period), alerts),
    [alerts, equipmentId, period]
  );
}
