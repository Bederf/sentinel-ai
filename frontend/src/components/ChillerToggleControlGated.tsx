/**
 * ChillerToggleControlGated - ChillerToggleControl wrapped with module gating
 *
 * Shows locked overlay if Controls module is inactive.
 * Shows normal chiller toggle if Controls module is active.
 */

import { ChillerToggleControl as ChillerToggleControlBase } from './ChillerToggleControl'
import { LockedFeatureOverlay } from './LockedFeatureOverlay'

interface ChillerToggleControlGatedProps {
  deviceId: string
  point: {
    id: string
    name: string
    value: number
    type: string
    unit?: string
    min_value?: number
    max_value?: number
    states?: { [key: number]: string }
  }
  onUpdate?: (value: number) => void
  disabled?: boolean
  /** Whether to apply module gating (default: true) */
  gated?: boolean
}

/**
 * Chiller toggle control with optional module gating.
 *
 * If gated=true and Controls module is inactive, shows upgrade prompt.
 * If gated=false or Controls module is active, shows normal toggle.
 *
 * @example
 * <ChillerToggleControlGated
 *   deviceId="chiller-001"
 *   point={{ id: '1', name: 'status', value: 1, type: 'switch' }}
 *   onUpdate={handleUpdate}
 *   gated={true}  // Enable module gating
 * />
 */
export function ChillerToggleControlGated({
  deviceId,
  point,
  onUpdate,
  disabled = false,
  gated = true,
}: ChillerToggleControlGatedProps) {
  const control = (
    <ChillerToggleControlBase
      deviceId={deviceId}
      point={point}
      onUpdate={onUpdate}
      disabled={disabled}
    />
  )

  if (!gated) {
    return control
  }

  return (
    <LockedFeatureOverlay
      module="control"
      featureName="Chiller Control"
      customMessage="Enable Controls module to let SENTINEL automatically manage chiller operations, reduce cycling losses, and lower energy costs by 10-15%."
    >
      {control}
    </LockedFeatureOverlay>
  )
}

export default ChillerToggleControlGated
