/**
 * ThermalOptimizationPanelGated - Module-gated HVAC thermal optimization
 *
 * Wraps ThermalOptimizationPanel with LockedFeatureOverlay to gate behind CONTROL module.
 * Shows temperature curves and pre-cooling schedules when module active.
 * When inactive, displays upgrade prompt with HVAC efficiency savings.
 *
 * Usage: Same as ThermalOptimizationPanel, add gated prop to optionally bypass gating
 */

import { ThermalOptimizationPanel } from './ThermalOptimizationPanel'
import { LockedFeatureOverlay } from '../LockedFeatureOverlay'

interface ThermalOptimizationPanelGatedProps {
  siteId: string
  compact?: boolean
  /** Whether to apply module gating (default: true) */
  gated?: boolean
  /** Optional pre-computed thermal runway from scenario data. */
  scenarioRunwayMetrics?: {
    without_precooling: number;
    with_precooling: number;
    comfort_breach_time?: string;
  };
}

export function ThermalOptimizationPanelGated({
  siteId,
  compact = false,
  gated = true,
  scenarioRunwayMetrics,
}: ThermalOptimizationPanelGatedProps) {
  if (!gated) {
    // Bypass gating for backward compatibility
    return <ThermalOptimizationPanel siteId={siteId} compact={compact} scenarioRunwayMetrics={scenarioRunwayMetrics} />
  }

  return (
    <LockedFeatureOverlay
      module="hvac_control"
      featureName="Thermal Optimization"
      customMessage="Enable Controls module to let SENTINEL predict and prevent thermal runway through proactive pre-cooling — reduce peak demand by 15-20% and maintain optimal occupant comfort."
    >
      <ThermalOptimizationPanel siteId={siteId} compact={compact} scenarioRunwayMetrics={scenarioRunwayMetrics} />
    </LockedFeatureOverlay>
  )
}

export default ThermalOptimizationPanelGated
