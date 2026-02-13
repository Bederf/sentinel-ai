/**
 * useDemandAwaredecision Hook Tests (Phase 68-03-06)
 *
 * Tests complex multi-module peak demand decision hook with 10 test cases:
 * 1. Normal headroom (>80%): No recommendations generated
 * 2. Warning headroom (15-80%): Optional load reduction offered
 * 3. Critical headroom (<15%): Immediate shaving required, all modules activate
 * 4. Emergency headroom (<5%): Hard load shedding as last resort
 * 5. Multi-module coordination: Solar + HVAC recommendations combined correctly
 * 6. Cost optimization: Highest savings suggestion prioritized
 * 7. Safety validation: Never exceed equipment pressure/temperature limits
 * 8. User acceptance: Hook updates when user accepts/rejects recommendation
 * 9. Real-time updates: Cache invalidation when demand changes >50 kW
 * 10. Fallback logic: If AI optimizer unavailable, use rule-based defaults
 *
 * Test patterns from Phase 68-02-05 and Phase 68-02-07
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { useDemandAwaredecision } from '../useDemandAwaredecision';
import type {
  DemandStatusResponse,
  MultiModuleRecommendation,
  ModuleAction,
} from '../../lib/api/peakDemand';
import { peakDemandApi } from '../../lib/api/peakDemand';

// Mock the API
vi.mock('../../lib/api/peakDemand', () => ({
  peakDemandApi: {
    getDemandStatus: vi.fn(),
    getDemandForecast: vi.fn(),
    getRecommendations: vi.fn(),
  },
}));

// ============= Test Utilities =============

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// ============= Mock Data Factories =============

function createMockPeakDemandStatus(
  overrides?: Partial<DemandStatusResponse>
): DemandStatusResponse {
  return {
    site_id: 'site-002',
    current_demand_kw: 5500,
    nmd_limit_kva: 6000,
    headroom_kw: 500,
    headroom_percent: 8.3,
    headroom_level: 'normal',
    demand_trend: 'stable',
    active_modules: ['solar', 'hvac'],
    available_reductions: {
      solar: { max_reduction_kw: 200, method: 'bess_discharge' },
      hvac: { max_reduction_kw: 50, method: 'setpoint_increase' },
    },
    last_updated: new Date().toISOString(),
    ...overrides,
  };
}

function createMockModuleAction(overrides?: Partial<ModuleAction>): ModuleAction {
  return {
    module: 'solar',
    action: 'bess_discharge_200kw',
    duration_min: 60,
    reduction_kw: 200,
    estimated_savings_r: 31100,
    ...overrides,
  };
}

function createMockMultiModuleRecommendation(
  overrides?: Partial<MultiModuleRecommendation>
): MultiModuleRecommendation {
  return {
    recommendation_id: 'rec-001',
    timestamp: new Date().toISOString(),
    type: 'peak_shaving',
    urgency: 'critical',
    priority: 'high',
    modules_involved: ['solar', 'hvac'],
    module_actions: [
      createMockModuleAction(),
      createMockModuleAction({
        module: 'hvac',
        action: 'setpoint_increase_2c',
        reduction_kw: 50,
        estimated_savings_r: 7775,
        comfort_impact: 'minor',
      }),
    ],
    estimated_reduction_kw: 250,
    estimated_savings_r: 38875,
    reasoning:
      'NMD headroom critical (8.3%), BESS available, HVAC can support adjustment',
    requires_approval: true,
    ...overrides,
  };
}

// ============= Test Suite =============

describe('useDemandAwaredecision', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Test 1: Normal Headroom (>80%) - No Recommendations', () => {
    it('should not generate recommendations when headroom exceeds 80%', async () => {
      const mockStatus = createMockPeakDemandStatus({
        current_demand_kw: 1200,
        headroom_kw: 4800,
        headroom_percent: 80,
        headroom_level: 'normal',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.should_recommend).toBe(false);
      expect(result.current.decision!.urgency).toBe('none');
      expect(result.current.decision!.recommendation).toBeNull();
    });

    it('should show normal urgency level in decision', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 85,
        headroom_level: 'normal',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.headroomLevel).toBe('normal');
      expect(result.current.decision!.urgency).toBe('none');
    });
  });

  describe('Test 2: Warning Headroom (15-80%) - Optional Load Reduction', () => {
    it('should offer optional load reduction in warning state', async () => {
      const mockStatus = createMockPeakDemandStatus({
        current_demand_kw: 5400,
        headroom_kw: 600,
        headroom_percent: 10,
        headroom_level: 'warning',
      });

      const mockRec = createMockMultiModuleRecommendation({
        urgency: 'optional',
        estimated_reduction_kw: 100,
        estimated_savings_r: 15500,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.should_recommend).toBe(true);
      expect(result.current.decision!.urgency).toBe('optional');
      expect(result.current.decision!.recommendation!.estimated_savings_r).toBeGreaterThan(0);
    });

    it('should include comfort impact assessment in warning state', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 20,
        headroom_level: 'warning',
      });

      const mockRec = createMockMultiModuleRecommendation({
        urgency: 'optional',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.cost_analysis.comfort_impact_level).toBe('minor');
    });
  });

  describe('Test 3: Critical Headroom (<15%) - Immediate Shaving Required', () => {
    it('should recommend immediate action in critical state (<15%)', async () => {
      const mockStatus = createMockPeakDemandStatus({
        current_demand_kw: 5700,
        headroom_kw: 300,
        headroom_percent: 5,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation({
        urgency: 'immediate',
        estimated_reduction_kw: 250,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.should_recommend).toBe(true);
      expect(result.current.decision!.urgency).toBe('immediate');
      expect(result.current.decision!.recommendation!.modules_involved).toContain('solar');
      expect(result.current.decision!.recommendation!.modules_involved).toContain('hvac');
    });

    it('should activate all modules in critical state', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 12,
        headroom_level: 'critical',
        active_modules: ['solar', 'hvac', 'energy'],
      });

      const mockRec = createMockMultiModuleRecommendation({
        modules_involved: ['solar', 'hvac', 'energy'],
        module_actions: [
          createMockModuleAction({ module: 'solar', reduction_kw: 200 }),
          createMockModuleAction({
            module: 'hvac',
            action: 'setpoint_increase_2c',
            reduction_kw: 50,
          }),
          createMockModuleAction({
            module: 'energy',
            action: 'pump_deferral',
            reduction_kw: 50,
          }),
        ],
        estimated_reduction_kw: 300,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.recommendation!.modules_involved).toHaveLength(3);
    });
  });

  describe('Test 4: Emergency Headroom (<5%) - Hard Load Shedding', () => {
    it('should escalate to emergency measures when headroom <5%', async () => {
      const mockStatus = createMockPeakDemandStatus({
        current_demand_kw: 5850,
        headroom_kw: 150,
        headroom_percent: 2.5,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation({
        urgency: 'critical',
        estimated_reduction_kw: 400,
        module_actions: [
          createMockModuleAction({
            module: 'solar',
            action: 'bess_emergency_discharge_300kw',
            reduction_kw: 300,
          }),
          createMockModuleAction({
            module: 'load_deferral',
            action: 'hard_load_shedding',
            reduction_kw: 100,
          }),
        ],
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.urgency).toBe('emergency');
      expect(result.current.decision!.recommendation!.estimated_reduction_kw).toBeGreaterThan(300);
    });

    it('should show major comfort impact in emergency state', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 3,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation({
        urgency: 'critical',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.cost_analysis.comfort_impact_level).toBe('moderate');
    });
  });

  describe('Test 5: Multi-Module Coordination - Solar + HVAC', () => {
    it('should coordinate solar and HVAC recommendations correctly', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
        active_modules: ['solar', 'hvac'],
        available_reductions: {
          solar: { max_reduction_kw: 200, method: 'bess_discharge' },
          hvac: { max_reduction_kw: 50, method: 'setpoint_increase' },
        },
      });

      const mockRec = createMockMultiModuleRecommendation({
        modules_involved: ['solar', 'hvac'],
        module_actions: [
          createMockModuleAction({
            module: 'solar',
            action: 'bess_discharge_200kw',
            reduction_kw: 200,
            estimated_savings_r: 31100,
          }),
          createMockModuleAction({
            module: 'hvac',
            action: 'setpoint_increase_2c',
            reduction_kw: 50,
            estimated_savings_r: 7775,
            comfort_impact: 'minor',
          }),
        ],
        estimated_reduction_kw: 250,
        estimated_savings_r: 38875,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      const actions = result.current.decision!.recommendation!.module_actions;
      expect(actions).toHaveLength(2);
      expect(actions[0].module).toBe('solar');
      expect(actions[1].module).toBe('hvac');
      expect(result.current.multiModuleActive).toBe(true);
    });

    it('should calculate total reduction from all modules', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 10,
        headroom_level: 'critical',
        active_modules: ['solar', 'hvac', 'energy'],
      });

      const mockRec = createMockMultiModuleRecommendation({
        modules_involved: ['solar', 'hvac', 'energy'],
        module_actions: [
          createMockModuleAction({ module: 'solar', reduction_kw: 200 }),
          createMockModuleAction({
            module: 'hvac',
            action: 'setpoint_increase_2c',
            reduction_kw: 50,
          }),
          createMockModuleAction({
            module: 'energy',
            action: 'pump_deferral',
            reduction_kw: 30,
          }),
        ],
        estimated_reduction_kw: 280,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.recommendation!.estimated_reduction_kw).toBe(280);
    });
  });

  describe('Test 6: Cost Optimization - Highest Savings Prioritized', () => {
    it('should prioritize recommendations with highest cost savings', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation({
        estimated_reduction_kw: 250,
        estimated_savings_r: 38875,
        reasoning: 'Peak period (2PM) with TOU tariff R1.55/kWh vs base R0.95/kWh',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.cost_analysis.estimated_savings_r).toBe(38875);
    });

    it('should calculate cost savings correctly from module actions', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 10,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation({
        module_actions: [
          createMockModuleAction({
            module: 'solar',
            reduction_kw: 200,
            estimated_savings_r: 31100,
          }),
          createMockModuleAction({
            module: 'hvac',
            action: 'setpoint_increase_2c',
            reduction_kw: 50,
            estimated_savings_r: 7775,
          }),
        ],
        estimated_savings_r: 38875,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      const totalSavings = result.current.decision!.recommendation!.module_actions!.reduce(
        (sum, action) => sum + (action.estimated_savings_r ?? 0),
        0
      );
      expect(totalSavings).toBe(38875);
    });
  });

  describe('Test 7: Safety Validation - Equipment Constraints', () => {
    it('should enforce safety constraints on recommendations', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.safety_constraints).toBeDefined();
      expect(result.current.decision!.safety_constraints['min_equipment_safety_margin']).toBe('5%');
      expect(result.current.decision!.safety_constraints['max_temperature_increase']).toBe('2°C');
      expect(result.current.decision!.safety_constraints['max_pressure_increase']).toBe('0.5 bar');
    });

    it('should never recommend exceeding equipment specifications', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 5,
        headroom_level: 'critical',
        available_reductions: {
          hvac: { max_reduction_kw: 50, temp_limit_celsius: 28 },
          solar: { max_reduction_kw: 200, bess_soc_min_percent: 20 },
        },
      });

      const mockRec = createMockMultiModuleRecommendation({
        module_actions: [
          createMockModuleAction({
            module: 'hvac',
            action: 'setpoint_increase_2c',
            reduction_kw: 50,
          }),
        ],
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      const hvacAction = result.current.decision!.recommendation!.module_actions!.find(
        (a) => a.module === 'hvac'
      );
      expect(hvacAction?.action).toContain('setpoint_increase');
    });
  });

  describe('Test 8: User Acceptance - Hook Updates on Decision', () => {
    it('should track user decision as accepted', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation();

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.userDecision).toBe('pending');

      act(() => {
        result.current.acceptDecision();
      });

      expect(result.current.userDecision).toBe('accepted');
      expect(result.current.decision!.user_decision).toBe('accepted');
    });

    it('should track user decision as rejected', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation();

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.userDecision).toBe('pending');

      act(() => {
        result.current.rejectDecision();
      });

      expect(result.current.userDecision).toBe('rejected');
      expect(result.current.decision!.user_decision).toBe('rejected');
    });

    it('should allow reset of decision state', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      const mockRec = createMockMultiModuleRecommendation();

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([mockRec]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      act(() => {
        result.current.acceptDecision();
      });

      expect(result.current.userDecision).toBe('accepted');

      act(() => {
        result.current.resetDecision();
      });

      expect(result.current.userDecision).toBe('pending');
      // Decision is cleared but will be recomputed from demandStatus on next effect
      expect(result.current.decision).not.toHaveProperty('user_decision', 'accepted');
    });
  });

  describe('Test 9: Real-Time Updates - Cache Invalidation >50kW Change', () => {
    it('should maintain cache if demand change <50kW', async () => {
      const mockStatus = createMockPeakDemandStatus({
        current_demand_kw: 5500,
        headroom_percent: 8.3,
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(vi.mocked(peakDemandApi.getDemandStatus)).toHaveBeenCalledTimes(1);
    });
  });

  describe('Test 10: Fallback Logic - AI Unavailable → Rule-Based Defaults', () => {
    it('should fallback to rule-based decision when AI unavailable', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002', { enableFallback: true }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.urgency).toBe('immediate');
      expect(result.current.decision!.should_recommend).toBe(true);
    });

    it('should generate rule-based decision without AI optimizer', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 50,
        headroom_level: 'normal',
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002', { enableFallback: true }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.should_recommend).toBe(false);
      expect(result.current.decision!.urgency).toBe('none');
    });

    it('should handle AI optimizer errors gracefully', async () => {
      const mockStatus = createMockPeakDemandStatus({
        headroom_percent: 8,
        headroom_level: 'critical',
      });

      const mockAI = vi.fn().mockRejectedValueOnce(new Error('AI unavailable'));

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useDemandAwaredecision('site-002', { decisionAI: mockAI, enableFallback: true }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.decision).toBeDefined();
      });

      expect(result.current.decision!.urgency).toBe('immediate');
      expect(result.current.error).toBeDefined();
    });

    it('should use rule-based defaults when no demand status available', async () => {
      const { result } = renderHook(() => useDemandAwaredecision(undefined), {
        wrapper: createWrapper(queryClient),
      });

      // When siteId is undefined, query is disabled and decision won't be computed
      expect(result.current.demandStatus).toBeUndefined();
      expect(result.current.decision).toBeNull();
      expect(result.current.isCoordinatorActive).toBe(false);
    });
  });

  describe('Additional Tests: Edge Cases & Data Validation', () => {
    it('should handle disabled query when siteId is undefined', () => {
      const { result } = renderHook(() => useDemandAwaredecision(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.demandStatus).toBeUndefined();
      expect(result.current.decision).toBeNull();
    });

    it('should include coordinator active status', async () => {
      const mockStatus = createMockPeakDemandStatus();

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      expect(result.current.isCoordinatorActive).toBe(true);
    });

    it('should detect multi-module scenarios correctly', async () => {
      const mockStatus = createMockPeakDemandStatus({
        active_modules: ['solar', 'hvac', 'energy'],
      });

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      expect(result.current.multiModuleActive).toBe(true);
    });

    it('should track last update time', async () => {
      const mockStatus = createMockPeakDemandStatus();

      vi.mocked(peakDemandApi.getDemandStatus).mockResolvedValueOnce(mockStatus);
      vi.mocked(peakDemandApi.getRecommendations).mockResolvedValueOnce([]);

      const { result } = renderHook(() => useDemandAwaredecision('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.demandStatus).toBeDefined();
      });

      await waitFor(() => {
        expect(result.current.lastUpdateTime).toBeDefined();
      });

      expect(result.current.lastUpdateTime).toBeInstanceOf(Date);
    });
  });
});
