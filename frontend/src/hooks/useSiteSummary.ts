import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api/fetchClient';

/**
 * Site summary response type
 */
interface SafetySummary {
  total: number;
  safe: number;
  warning: number;
  blocked: number;
  alarm: number;
}

interface AlertSummary {
  critical: number;
  warning: number;
  info: number;
}

interface PredictionSummary {
  high_risk: number;
  medium_risk: number;
  low_risk: number;
}

interface EnergySummary {
  current_kw: number;
  today_kwh: number;
}

export interface SiteSummary {
  site_id: string;
  site_name: string;
  equipment_count: number;
  equipment_by_type: Record<string, number>;
  safety: SafetySummary;
  alerts: AlertSummary;
  predictions: PredictionSummary;
  energy: EnergySummary;
  last_updated: string;
}

/**
 * Hook to fetch aggregated site summary
 * Single query returns equipment count, safety status, alerts, predictions
 * Cache: 30s staleTime, 5m gcTime
 */
export function useSiteSummary(
  siteId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: ['site-summary', siteId],
    queryFn: () => apiFetch<SiteSummary>(`/api/sites/${siteId}/summary`),
    staleTime: 30 * 1000, // 30s
    gcTime: 5 * 60 * 1000, // 5m
    enabled: options?.enabled !== false,
  });
}
