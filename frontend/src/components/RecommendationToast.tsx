import { useEffect } from 'react';
import * as React from 'react';
import { Lightbulb, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';

interface RecommendationData {
  id: string;
  status: string;
  title: string;
  description?: string;
  equipment_name?: string;
}

/**
 * Hook that polls for new recommendations and shows toast notifications.
 * 
 * Shows a toast notification when:
 * - Simulation is running
 * - New recommendations appear (status === 'PENDING')
 * - User hasn't already seen this recommendation
 * 
 * Usage:
 * ```
 * function Dashboard() {
 *   useRecommendationToasts('site-002');
 *   return <div>...</div>;
 * }
 * ```
 */
export function useRecommendationToasts(siteId: string, pollingIntervalMs = 30000) {
  useEffect(() => {
    const shownToastIds = new Set<string>();

    // Poll for new recommendations every 30 seconds
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/recommendations/${siteId}`);
        const data = await response.json();

        const pending: RecommendationData[] = data.recommendations?.filter(
          (r: RecommendationData) => r.status === 'PENDING'
        ) || [];

        if (pending.length > 0) {
          // Show toast for each new recommendation
          for (const rec of pending) {
            if (!shownToastIds.has(rec.id)) {
              shownToastIds.add(rec.id);

              toast("New AI Recommendation", {
                description: rec.equipment_name
                  ? `${rec.title} • ${rec.equipment_name}`
                  : rec.title,
                duration: 8000,
                icon: <Lightbulb className="h-4 w-4" />,
              });
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch recommendations:', error);
      }
    }, pollingIntervalMs);

    return () => clearInterval(interval);
  }, [siteId, pollingIntervalMs]);
}

/**
 * Simple component that renders recommendation count badge.
 * 
 * Usage:
 * ```
 * <RecommendationBadge siteId="site-002" />
 * ```
 */
export function RecommendationBadge({ siteId }: { siteId: string }) {
  const [pendingCount, setPendingCount] = React.useState(0);

  React.useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/recommendations/${siteId}`);
        const data = await response.json();
        const pending = data.recommendations?.filter((r: RecommendationData) => r.status === 'PENDING') || [];
        setPendingCount(pending.length);
      } catch (error) {
        console.error('Failed to fetch recommendation count:', error);
      }
    }, 30000);

    return () => clearInterval(timer);
  }, [siteId]);

  if (pendingCount === 0) return null;

  return (
    <div className="absolute top-2 right-2 bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold">
      {pendingCount}
    </div>
  );
}
