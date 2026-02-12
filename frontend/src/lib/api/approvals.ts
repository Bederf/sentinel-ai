/**
 * Approval Workflow API Client
 *
 * Handles Tier 2 (supervised) approval workflow for Niagara equipment control.
 * Provides methods to approve, reject, and check status of equipment control recommendations.
 */

import { fetchApi } from './client'

export interface ApprovalRequest {
  approved_by: string
  approval_notes?: string
}

export interface RejectionRequest {
  rejected_by: string
  reason: string
}

export interface ApprovalResponse {
  success: boolean
  recommendation_id: string
  status: string
  executed_at?: string
  error_message?: string
  cov_verified: boolean
  execution_result?: {
    success: boolean
    device_write: { success: boolean }
    cov_verified: boolean
    timestamp: string
  }
}

export interface ApprovalStatus {
  recommendation_id: string
  approval_status: string
  approved_by?: string
  approved_at?: string
  executed_at?: string
  rejection_reason?: string
}

export const approvalsApi = {
  /**
   * Approve a recommendation and execute device control.
   * Triggers SafetyEngine validation and device write via Niagara.
   */
  approveRecommendation: (
    recommendationId: string,
    approvedBy: string,
    approvalNotes?: string
  ) =>
    fetchApi<ApprovalResponse>(
      `/api/approvals/recommendations/${recommendationId}/approve`,
      {
        method: 'POST',
        body: JSON.stringify({
          approved_by: approvedBy,
          approval_notes: approvalNotes,
        }),
      }
    ),

  /**
   * Reject a pending recommendation.
   * Records rejection reason and creates audit log entry.
   */
  rejectRecommendation: (
    recommendationId: string,
    rejectedBy: string,
    reason: string
  ) =>
    fetchApi<ApprovalResponse>(
      `/api/approvals/recommendations/${recommendationId}/reject`,
      {
        method: 'POST',
        body: JSON.stringify({
          rejected_by: rejectedBy,
          reason,
        }),
      }
    ),

  /**
   * Get current approval status of a recommendation.
   */
  getApprovalStatus: (recommendationId: string) =>
    fetchApi<ApprovalStatus>(
      `/api/approvals/recommendations/${recommendationId}/status`
    ),
}
