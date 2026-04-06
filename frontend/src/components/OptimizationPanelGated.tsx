/**
 * OptimizationPanelGated - Module-gated optimization dashboard
 *
 * Wraps OptimizationPanel with LockedFeatureOverlay to gate behind CONTROL module.
 * Shows Eskom status, thermal runway, and pre-cooling optimization when module active.
 * When inactive, displays upgrade prompt with savings data.
 *
 * Usage: Same as OptimizationPanel, add gated prop to optionally bypass gating
 */

import { OptimizationPanel } from './OptimizationPanel'
import { LockedFeatureOverlay } from './LockedFeatureOverlay'

interface OptimizationPanelGatedProps {
  siteId?: string
  scenarioId?: string
  compact?: boolean
  /** Whether to apply module gating (default: true) */
  gated?: boolean
}

export function OptimizationPanelGated({
  siteId = '',
  scenarioId,
  compact = false,
  gated = true,
}: OptimizationPanelGatedProps) {
  if (!gated) {
    // Bypass gating for backward compatibility
    return <OptimizationPanel siteId={siteId} scenarioId={scenarioId} compact={compact} />
  }

  return (
    <LockedFeatureOverlay
      module="energy_control"
      featureName="Load Shedding Optimization"
      customMessage="Enable Controls module to let SENTINEL automatically pre-cool your building and reduce load during peak demand — save R8K-12K per load shedding event."
    >
      <OptimizationPanel siteId={siteId} scenarioId={scenarioId} compact={compact} />
    </LockedFeatureOverlay>
  )
}

export default OptimizationPanelGated
