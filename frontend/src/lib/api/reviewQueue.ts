/**
 * Review Queue API Client
 *
 * Phase 162: Semantic Control Foundation — Plan 05.
 * Human-in-the-loop review interface for semantic classification decisions.
 */

import { fetchApi } from "./client";

export interface ReviewQueueEntry {
  id: string;
  site_id: string;
  equipment_id: string;
  point_id: string;
  classification_id: string;
  semantic_tags: string[];
  confidence_score: number;
  confidence_level: string; // HIGH, MEDIUM, LOW
  safety_class: string; // LOW, MEDIUM, HIGH
  automation_tier: string; // observe_only, supervised, automatic
  validation_passed: boolean;
  validation_errors: unknown[];
  completeness_score: number | null;
  status: string; // pending, approved, rejected, overridden
  priority: number;
  classified_by: string;
  classified_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  decision_reason: string | null;
  override_tags: string[] | null;
  override_justification: string | null;
}

export interface ReviewQueueStats {
  total_pending: number;
  by_safety_class: Record<string, number>;
  by_confidence_level: Record<string, number>;
  avg_age_hours: number;
  high_priority_count: number;
}

export interface ReviewDecisionResponse {
  entry_id: string;
  success: boolean;
  message: string;
}

export interface BulkDecisionResponse {
  approved_count: number;
  message: string;
}

export interface PendingFilters {
  site_id: string;
  safety_class?: string;
  equipment_id?: string;
  confidence_threshold?: number;
  limit?: number;
}

export const reviewQueueApi = {
  async getPending(filters: PendingFilters): Promise<ReviewQueueEntry[]> {
    const params = new URLSearchParams({ site_id: filters.site_id });
    if (filters.safety_class) params.set("safety_class", filters.safety_class);
    if (filters.equipment_id) params.set("equipment_id", filters.equipment_id);
    if (filters.confidence_threshold !== undefined) {
      params.set("confidence_threshold", String(filters.confidence_threshold));
    }
    if (filters.limit !== undefined) {
      params.set("limit", String(filters.limit));
    }
    return fetchApi<ReviewQueueEntry[]>(`/api/review-queue/pending?${params.toString()}`);
  },

  async getStats(site_id: string): Promise<ReviewQueueStats> {
    return fetchApi<ReviewQueueStats>(`/api/review-queue/stats?site_id=${encodeURIComponent(site_id)}`);
  },

  async approve(entry_id: string, review_notes: string): Promise<ReviewDecisionResponse> {
    return fetchApi<ReviewDecisionResponse>(`/api/review-queue/${encodeURIComponent(entry_id)}/approve`, {
      method: "POST",
      body: JSON.stringify({ review_notes }),
    });
  },

  async reject(entry_id: string, reason: string, review_notes: string): Promise<ReviewDecisionResponse> {
    return fetchApi<ReviewDecisionResponse>(`/api/review-queue/${encodeURIComponent(entry_id)}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason, review_notes }),
    });
  },

  async override(
    entry_id: string,
    correct_tags: string[],
    justification: string
  ): Promise<ReviewDecisionResponse> {
    return fetchApi<ReviewDecisionResponse>(`/api/review-queue/${encodeURIComponent(entry_id)}/override`, {
      method: "POST",
      body: JSON.stringify({ correct_tags, justification }),
    });
  },

  async bulkApprove(entry_ids: string[]): Promise<BulkDecisionResponse> {
    return fetchApi<BulkDecisionResponse>("/api/review-queue/bulk-approve", {
      method: "POST",
      body: JSON.stringify({ entry_ids }),
    });
  },

  async getHistory(entry_id: string): Promise<unknown[]> {
    return fetchApi<unknown[]>(`/api/review-queue/${encodeURIComponent(entry_id)}/history`);
  },
};
