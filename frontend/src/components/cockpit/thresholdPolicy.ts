import type { HealthThresholds, RiskThresholds } from '@/lib/api';

export interface CockpitThresholdPolicy {
  health: HealthThresholds;
  risk: RiskThresholds;
  source: 'default' | 'settings';
}

export const DEFAULT_HEALTH_THRESHOLDS: HealthThresholds = {
  healthy: 80,
  warning: 60,
  critical: 0,
};

export const DEFAULT_RISK_THRESHOLDS: RiskThresholds = {
  medium: 31,
  high: 61,
  critical: 81,
};

export const DEFAULT_COCKPIT_THRESHOLD_POLICY: CockpitThresholdPolicy = {
  health: DEFAULT_HEALTH_THRESHOLDS,
  risk: DEFAULT_RISK_THRESHOLDS,
  source: 'default',
};
