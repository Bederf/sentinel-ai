/**
 * OptimizationToggleGated - Module-gated optimization enable/disable toggle
 *
 * Wraps OptimizationToggle with LockedFeatureOverlay to gate behind CONTROL module.
 * When CONTROL is inactive, shows upgrade prompt with energy savings data.
 *
 * Usage: Same as OptimizationToggle, add gated prop to optionally bypass gating
 */

import { OptimizationToggle } from './OptimizationToggle'
import { LockedFeatureOverlay } from './LockedFeatureOverlay'

interface OptimizationToggleGatedProps {
  siteId: string
  enabled: boolean
  onToggle?: (enabled: boolean) => void
  disabled?: boolean
  className?: string
  /** Whether to apply module gating (default: true) */
  gated?: boolean
}

export function OptimizationToggleGated({
  siteId,
  enabled,
  onToggle,
  disabled = false,
  className = '',
  gated = true,
}: OptimizationToggleGatedProps) {
  if (!gated) {
    // Bypass gating for backward compatibility
    return (
      <OptimizationToggle
        siteId={siteId}
        enabled={enabled}
        onToggle={onToggle}
        disabled={disabled}
        className={className}
      />
    )
  }

  return (
    <LockedFeatureOverlay
      module="energy_control"
      featureName="AI Optimization"
      customMessage="Enable Controls module to let SENTINEL automatically optimize your building operations based on occupancy, weather, and energy pricing — estimated R15K+/month in savings."
    >
      <OptimizationToggle
        siteId={siteId}
        enabled={enabled}
        onToggle={onToggle}
        disabled={disabled}
        className={className}
      />
    </LockedFeatureOverlay>
  )
}

export default OptimizationToggleGated
