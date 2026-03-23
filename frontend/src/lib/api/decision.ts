/**
 * Decision Execution API Client
 *
 * Handles Phase 170 supervised control execution flow:
 * - POST /api/v1/approval/execute/{site_id} to dispatch control command
 * - Returns ACCEPTED immediately (async verification in background)
 * - SSE stream provides verification updates: VERIFIED, TIMEOUT, or ERROR
 *
 * Phase 170-02: Control Actuation Loop — First live supervised execution
 */

import { fetchApi } from './client'

/**
 * Execution states for a control decision
 */
export type ExecutionState = 'pending' | 'accepted' | 'verified' | 'timeout' | 'error'

/**
 * Frontend representation of a decision (minimal for approval UI)
 */
export interface Decision {
  id: string
  site_id: string
  device_id: string
  point: string
  command_value: number | boolean | string
  tier: number // 1 (MEDIUM), 2 (HIGH), 3 (CRITICAL)
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  created_at: string
}

/**
 * Request body for POST /api/v1/approval/execute/{site_id}
 */
export interface ApprovalExecutionRequest {
  decision_id: string
  approval_outcome: 'approved' | 'rejected'
}

/**
 * Response from POST /api/v1/approval/execute/{site_id}
 * Returns ACCEPTED immediately (does NOT wait for verification)
 */
export interface ApprovalExecutionResponse {
  status: 'ACCEPTED' // Immediate response
  decision_id: string
  correlation_id: string // Threaded through entire 14-step flow
  message: string
  estimated_verification_time_seconds: number
}

/**
 * Verification event from SSE stream
 * Sent after command is dispatched to device
 */
export interface ExecutionEvent {
  event_type: 'COMMAND_ACCEPTED' | 'COMMAND_VERIFIED' | 'COMMAND_TIMEOUT' | 'COMMAND_FAILED'
  decision_id: string
  correlation_id: string
  timestamp: string
  details?: {
    device_id?: string
    point?: string
    expected_value?: number | boolean | string
    actual_value?: number | boolean | string
    error_message?: string
  }
}

/**
 * Client-side execution state (local)
 */
export interface ExecutionProgress {
  state: ExecutionState
  decision_id: string
  correlation_id?: string
  timestamp: number
  message?: string
  error?: string
}

export const decisionApi = {
  /**
   * Execute a decision (dispatch command to BMS)
   * Returns ACCEPTED immediately; verification happens asynchronously via SSE
   */
  executeDecision: (
    siteId: string,
    decisionId: string,
    approvalOutcome: 'approved' | 'rejected'
  ) =>
    fetchApi<ApprovalExecutionResponse>(
      `/api/v1/approval/execute/${siteId}`,
      {
        method: 'POST',
        body: JSON.stringify({
          decision_id: decisionId,
          approval_outcome: approvalOutcome,
        }),
      }
    ),
}
