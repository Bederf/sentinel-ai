/**
 * TemperatureControlGated - TemperatureControl wrapped with module gating
 * 
 * Shows locked overlay if Controls module is inactive.
 * Shows normal temperature control if Controls module is active.
 */

import { TemperatureControl as TemperatureControlBase } from './TemperatureControl'
import { LockedFeatureOverlay } from './LockedFeatureOverlay'

interface TemperatureControlGatedProps {
  label: string
  unit: string
  value: number
  min?: number
  max?: number
  step?: number
  onChange: (value: number) => void
  disabled?: boolean
  error?: string | null
  /** Whether to apply module gating (default: true) */
  gated?: boolean
}

/**
 * Temperature control with optional module gating.
 * 
 * If gated=true and Controls module is inactive, shows upgrade prompt.
 * If gated=false or Controls module is active, shows normal control.
 * 
 * @example
 * <TemperatureControlGated
 *   label="Zone A Setpoint"
 *   unit="°C"
 *   value={22}
 *   onChange={setTemp}
 *   gated={true}  // Enable module gating
 * />
 */
export function TemperatureControlGated({
  label,
  unit,
  value,
  min = 18,
  max = 26,
  step = 0.5,
  onChange,
  disabled = false,
  error = null,
  gated = true,
}: TemperatureControlGatedProps) {
  const control = (
    <TemperatureControlBase
      label={label}
      unit={unit}
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={onChange}
      disabled={disabled}
      error={error}
    />
  )

  if (!gated) {
    return control
  }

  return (
    <LockedFeatureOverlay
      module="control"
      featureName={`${label} Control`}
      customMessage={`Enable Controls module to let SENTINEL automatically adjust ${label.toLowerCase()} and maintain optimal comfort while reducing energy costs.`}
    >
      {control}
    </LockedFeatureOverlay>
  )
}

export default TemperatureControlGated
