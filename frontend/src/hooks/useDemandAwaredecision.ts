/**
 * useDemandAwaredecision - Multi-Module Peak Demand Decision Hook
 *
 * Manages complex peak demand shaving recommendations considering:
 * - Current NMD headroom (kW), urgency level
 * - Active modules at site and available reductions
 * - Cost-benefit analysis (R savings vs comfort impact)
 * - Safety constraints (equipment specifications)
 * - Real-time user feedback (accept/reject)
 *
 * Stale time: 30s (coordinator runs every 5 minutes)
 */

import { useState, useCallback, useEffect } from 'react';
import { usePeakDemandStatus, usePeakDemandRecommendations } from './usePeakDemand';
import type { DemandStatusResponse, MultiModuleRecommendation } from '../lib/api/peakDemand';

export interface DecisionRequest {
  site_id: string;
  current_headroom_kw: number;
  headroom_level: 'normal' | 'caution' | 'warning' | 'critical';
  active_modules: string[];
  available_reductions: Record<string, any>;
  cost_per_kwh_r?: number; // Tariff in Rands per kWh
}

export interface DecisionResult {
  should_recommend: boolean;
  urgency: 'none' | 'optional' | 'immediate' | 'emergency';
  recommendation: MultiModuleRecommendation | null;
  safety_constraints: Record<string, string>;
  cost_analysis: {
    estimated_savings_r: number;
    comfort_impact_level: 'none' | 'minor' | 'moderate' | 'major';
  };
  user_decision?: 'pending' | 'accepted' | 'rejected';
  reasoning: string;
}

type DecisionAI = (request: DecisionRequest) => Promise<DecisionResult>;

interface UseDemandAwaredecisionOptions {
  decisionAI?: DecisionAI;
  enableFallback?: boolean;
}

/**
 * Default rule-based decision logic (used when AI unavailable)
 */
function getDefaultDecision(
  status: DemandStatusResponse | undefined,
  recommendation: MultiModuleRecommendation | null,
  userDecision: 'pending' | 'accepted' | 'rejected'
): DecisionResult {
  if (!status) {
    return {
      should_recommend: false,
      urgency: 'none',
      recommendation: null,
      safety_constraints: {},
      cost_analysis: { estimated_savings_r: 0, comfort_impact_level: 'none' },
      reasoning: 'No demand status available',
      user_decision: userDecision,
    };
  }

  // Determine urgency based on headroom level
  let shouldRecommend = false;
  let urgency: DecisionResult['urgency'] = 'none';
  let comfortImpact: DecisionResult['cost_analysis']['comfort_impact_level'] = 'none';

  if (status.headroom_level === 'critical' && status.headroom_percent < 15) {
    shouldRecommend = true;
    urgency = status.headroom_percent < 5 ? 'emergency' : 'immediate';
    comfortImpact = 'moderate';
  } else if (status.headroom_level === 'warning' && status.headroom_percent < 80) {
    shouldRecommend = true;
    urgency = 'optional';
    comfortImpact = 'minor';
  } else if (status.headroom_level === 'caution') {
    shouldRecommend = true;
    urgency = 'optional';
    comfortImpact = 'minor';
  }

  return {
    should_recommend: shouldRecommend,
    urgency,
    recommendation: recommendation && shouldRecommend ? recommendation : null,
    safety_constraints: {
      min_equipment_safety_margin: '5%',
      max_temperature_increase: '2°C',
      max_pressure_increase: '0.5 bar',
    },
    cost_analysis: {
      estimated_savings_r: recommendation?.estimated_savings_r ?? 0,
      comfort_impact_level: comfortImpact,
    },
    reasoning: `Headroom ${status.headroom_percent.toFixed(1)}% (${status.headroom_level}) - ${
      shouldRecommend
        ? `${urgency} action recommended`
        : 'no action needed'
    }`,
    user_decision: userDecision,
  };
}

/**
 * Hook: Generate peak demand shaving recommendations with decision logic
 *
 * Manages multi-module coordination, safety validation, and cost optimization.
 * Provides user feedback mechanism for accept/reject decisions.
 *
 * @param siteId - Site identifier for demand queries
 * @param options - Configuration (custom AI, fallback enablement)
 */
export function useDemandAwaredecision(
  siteId: string | undefined,
  options: UseDemandAwaredecisionOptions = {}
) {
  const { decisionAI, enableFallback = true } = options;

  // Fetch current demand status and recommendations
  const demandStatus = usePeakDemandStatus(siteId);
  const recommendations = usePeakDemandRecommendations(siteId);

  // Local state for decision management
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [userDecision, setUserDecision] = useState<'pending' | 'accepted' | 'rejected'>(
    'pending'
  );
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);

  /**
   * Compute decision based on current status and recommendations (async for AI)
   */
  const computeDecisionAsync = useCallback(async () => {
    if (!demandStatus.data) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const status = demandStatus.data;
      const recommendation = recommendations.data?.[0] || null;

      if (decisionAI && enableFallback) {
        // Use AI-driven decision
        const request: DecisionRequest = {
          site_id: siteId!,
          current_headroom_kw: status.headroom_kw,
          headroom_level: status.headroom_level,
          active_modules: status.active_modules,
          available_reductions: status.available_reductions,
        };

        const aiDecision = await decisionAI(request);
        setDecision({ ...aiDecision, user_decision: userDecision });
      } else {
        // Use rule-based fallback
        const fallbackDecision = getDefaultDecision(status, recommendation, userDecision);
        setDecision(fallbackDecision);
      }

      setLastUpdateTime(new Date());
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      setError(error);

      // Fallback to rule-based decision on AI failure
      if (enableFallback && demandStatus.data) {
        const recommendation = recommendations.data?.[0] || null;
        const fallbackDecision = getDefaultDecision(demandStatus.data, recommendation, userDecision);
        setDecision(fallbackDecision);
        setLastUpdateTime(new Date());
      }
    } finally {
      setIsLoading(false);
    }
  }, [demandStatus.data, recommendations.data, siteId, decisionAI, enableFallback, userDecision]);

  /**
   * Compute decision immediately when data loads (synchronous fallback)
   */
  const computeDecisionSync = useCallback(() => {
    if (!demandStatus.data) {
      setDecision(null);
      return;
    }

    const recommendation = recommendations.data?.[0] || null;
    const fallbackDecision = getDefaultDecision(demandStatus.data, recommendation, userDecision);
    setDecision(fallbackDecision);
    setLastUpdateTime(new Date());
  }, [demandStatus.data, recommendations.data, userDecision]);

  /**
   * Run decision computation on data load
   */
  useEffect(() => {
    if (!demandStatus.data) {
      return;
    }

    // Use AI if available, otherwise use fallback
    if (decisionAI && enableFallback) {
      void computeDecisionAsync();
    } else {
      computeDecisionSync();
    }
  }, [demandStatus.data, recommendations.data, decisionAI, enableFallback, computeDecisionAsync, computeDecisionSync]);

  /**
   * Handle user acceptance of recommendation
   */
  const acceptDecision = useCallback(() => {
    setUserDecision('accepted');
    if (decision) {
      setDecision({ ...decision, user_decision: 'accepted' });
    }
  }, [decision]);

  /**
   * Handle user rejection of recommendation
   */
  const rejectDecision = useCallback(() => {
    setUserDecision('rejected');
    if (decision) {
      setDecision({ ...decision, user_decision: 'rejected' });
    }
  }, [decision]);

  /**
   * Reset decision state
   */
  const resetDecision = useCallback(() => {
    setUserDecision('pending');
    setDecision(null);
    setError(null);
  }, []);

  return {
    // Data
    decision,
    isLoading: isLoading || demandStatus.isLoading,
    isError: demandStatus.isError || recommendations.isError || error !== null,
    error: error || demandStatus.error || recommendations.error,
    lastUpdateTime,

    // Demand status context
    demandStatus: demandStatus.data,
    headroomKw: demandStatus.data?.headroom_kw,
    headroomLevel: demandStatus.data?.headroom_level,
    headroomPercent: demandStatus.data?.headroom_percent,

    // User actions
    acceptDecision,
    rejectDecision,
    resetDecision,
    userDecision,

    // Metadata
    isCoordinatorActive: demandStatus.data !== undefined,
    multiModuleActive: (demandStatus.data?.active_modules?.length ?? 0) > 1,
  };
}
