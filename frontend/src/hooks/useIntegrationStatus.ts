/**
 * useIntegrationStatus - React Query hook for external integration health status
 */

import { useQuery } from '@tanstack/react-query';

export function useIntegrationStatus(siteId: string | undefined) {
  return useQuery({
    queryKey: ['integrations', 'status', siteId],
    queryFn: async () => {
      if (!siteId) return null;
      const response = await fetch(`/api/integrations/${siteId}/status`);
      if (!response.ok) throw new Error('Failed to fetch integration status');
      return response.json();
    },
    enabled: !!siteId,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}
