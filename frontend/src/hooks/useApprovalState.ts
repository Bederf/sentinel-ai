/**
 * React Query Hook for Approval Workflow State Management
 *
 * Manages recommendation approval workflow:
 * - Load pending recommendations from API
 * - Approve recommendations (status: PENDING → APPROVED → EXECUTED)
 * - Reject recommendations (status: PENDING → REJECTED)
 * - Rollback executed recommendations (status: EXECUTED → ROLLED_BACK)
 * - Track COV feedback (Change of Value verification)
 * - Monitor audit trail
 *
 * All state transitions stored in QueryClient cache and persisted to backend.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { approvalsApi } from '@/lib/api/approvals';
import { authorizedFetch } from '@/lib/api/client';

/**
 * Hook for managing approval workflow state
 *
 * @param siteId - Building identifier
 * @param enabled - Whether to enable fetching (default: true)
 * @returns Approval state object with recommendations and mutation handlers
 */
export function useApprovalState(siteId: string, enabled: boolean = true) {
  const queryClient = useQueryClient();
  const recommendationsEnabled = enabled && !!siteId && siteId !== 'site-001';

  // Fetch pending recommendations
  const recommendationsQuery = useQuery({
    queryKey: ['recommendations-pending', siteId],
    queryFn: async () => {
      // Placeholder: In real implementation, call API to fetch pending recommendations
      // For now, return empty array (tests will mock this)
      // Backend route: GET /api/modules/site/{site_id}/recommendations?status=pending
      const response = await authorizedFetch(`/api/modules/site/${siteId}/recommendations?status=pending`);
      if (!response.ok) throw new Error('Failed to fetch recommendations');
      const data = await response.json();
      // Backend returns a list directly, not wrapped in {recommendations: [...]}
      return Array.isArray(data) ? data : (data.recommendations || []);
    },
    staleTime: 30000, // 30 seconds (recommendations change frequently)
    gcTime: 5 * 60 * 1000, // 5 minutes (formerly cacheTime)
    enabled: recommendationsEnabled,
    retry: false,
  });

  // Approve recommendation mutation
  const approveMutation = useMutation({
    mutationFn: async ({
      recommendationId,
      approvedBy,
      approvalNotes,
    }: {
      recommendationId: string;
      approvedBy: string;
      approvalNotes?: string;
    }) => {
      return approvalsApi.approveRecommendation(recommendationId, approvedBy, approvalNotes);
    },
    onSuccess: (data, variables) => {
      // Invalidate cache to refetch
      queryClient.invalidateQueries({ queryKey: ['recommendations-pending', siteId] });
      queryClient.invalidateQueries({ queryKey: ['recommendation-status', variables.recommendationId] });
    },
  });

  // Reject recommendation mutation
  const rejectMutation = useMutation({
    mutationFn: async ({
      recommendationId,
      rejectedBy,
      reason,
    }: {
      recommendationId: string;
      rejectedBy: string;
      reason: string;
    }) => {
      return approvalsApi.rejectRecommendation(recommendationId, rejectedBy, reason);
    },
    onSuccess: (data, variables) => {
      // Invalidate cache to refetch
      queryClient.invalidateQueries({ queryKey: ['recommendations-pending', siteId] });
      queryClient.invalidateQueries({ queryKey: ['recommendation-status', variables.recommendationId] });
    },
  });

  // Get approval status for a specific recommendation
  const _statusQuery = useQuery({
    queryKey: ['recommendation-status', ''],
    queryFn: async (context) => {
      const [, recommendationId] = context.queryKey;
      if (!recommendationId) return null;
      return approvalsApi.getApprovalStatus(recommendationId);
    },
    enabled: false, // Manually enabled when needed
  });

  return {
    recommendations: recommendationsQuery.data || [],
    isLoading: recommendationsQuery.isLoading,
    error: recommendationsQuery.error,
    approve: approveMutation.mutate,
    approveAsync: approveMutation.mutateAsync,
    isApproving: approveMutation.isPending,
    reject: rejectMutation.mutate,
    rejectAsync: rejectMutation.mutateAsync,
    isRejecting: rejectMutation.isPending,
    getStatus: async (recommendationId: string) => {
      return approvalsApi.getApprovalStatus(recommendationId);
    },
    refetch: recommendationsQuery.refetch,
  };
}

/**
 * Hook for tracking approval execution state
 *
 * Monitors device write, COV feedback, and rollback operations.
 *
 * @param recommendationId - Recommendation UUID
 * @returns Execution state with COV verification and rollback capability
 */
export function useApprovalExecution(recommendationId: string) {
  const queryClient = useQueryClient();

  // Get execution status
  const executionQuery = useQuery({
    queryKey: ['approval-execution', recommendationId],
    queryFn: async () => {
      if (!recommendationId) return null;
      const response = await approvalsApi.getApprovalStatus(recommendationId);
      return response;
    },
    staleTime: 10000, // 10 seconds (execution is active)
    gcTime: 2 * 60 * 1000, // 2 minutes
    enabled: !!recommendationId,
  });

  // Rollback approved execution
  const rollbackMutation = useMutation({
    mutationFn: async ({
      recommendationId: recId,
      reason,
      initiatedBy,
    }: {
      recommendationId: string;
      reason?: string;
      initiatedBy: string;
    }) => {
      const response = await authorizedFetch(
        `/api/approvals/recommendations/${recId}/rollback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            rollback_reason: reason,
            initiated_by: initiatedBy,
          }),
        }
      );
      if (!response.ok) throw new Error('Rollback failed');
      return response.json();
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['approval-execution', variables.recommendationId] });
    },
  });

  return {
    execution: executionQuery.data,
    isLoading: executionQuery.isLoading,
    error: executionQuery.error,
    covVerified: executionQuery.data?.cov_verified ?? false,
    rollback: rollbackMutation.mutate,
    rollbackAsync: rollbackMutation.mutateAsync,
    isRollingBack: rollbackMutation.isPending,
    refetch: executionQuery.refetch,
  };
}
