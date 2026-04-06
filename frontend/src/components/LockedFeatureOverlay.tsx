/**
 * LockedFeatureOverlay Component
 *
 * Reusable wrapper that gates features by module activation.
 *
 * If module is active: renders child component normally
 * If module is inactive: renders greyed-out child + upgrade prompt with savings data
 *
 * Usage:
 * <LockedFeatureOverlay module="hvac_control" featureName="Temperature Setpoint">
 *   <TemperatureControl {...props} />
 * </LockedFeatureOverlay>
 */

import type { ReactNode } from 'react'
import React from 'react'
import { Lock } from 'lucide-react'
import { useModuleAccess, MODULE_DESCRIPTIONS } from '@/hooks/useModuleAccess'
import { formatCurrencyZAR, formatPercentage } from '@/lib/locale'

interface LockedFeatureOverlayProps {
  /** Module required to access this feature (e.g., 'control', 'maintenance', 'solar') */
  module: string

  /** Human-readable feature name for the prompt */
  featureName: string

  /** Child component(s) to render (shown normally if module active, greyed if inactive) */
  children: ReactNode

  /**
   * Whether to render children behind the locked overlay.
   * Set false for children with side effects (API calls, sockets) to avoid unnecessary requests.
   */
  renderPreviewWhenLocked?: boolean

  /** Optional custom message to show in upgrade prompt */
  customMessage?: string

  /** Optional callback when user clicks "Request Activation" */
  onRequestActivation?: () => void
}

/**
 * LockedFeatureOverlay - Smart feature gating with benefit-driven upgrade prompts
 */
export function LockedFeatureOverlay({
  module,
  featureName,
  children,
  customMessage,
  onRequestActivation,
  renderPreviewWhenLocked = true,
}: LockedFeatureOverlayProps) {
  const { isActive, loading, savingsData } = useModuleAccess(module)

  // If module is active or still loading auth check, show the feature normally
  if (isActive || loading) {
    return <>{children}</>
  }

  // Module is inactive: render greyed-out child with upgrade overlay
  return (
    <div className="relative">
      {/* Greyed-out child component */}
      {renderPreviewWhenLocked ? (
        <div className="opacity-40 pointer-events-none select-none">
          {children}
        </div>
      ) : (
        <div className="opacity-40 pointer-events-none select-none h-full min-h-[320px]" />
      )}

      {/* Upgrade prompt overlay */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="rounded-md p-6 max-w-sm mx-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          {/* Header with lock icon */}
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg" style={{ background: 'rgba(59, 130, 246, 0.1)' }}>
              <Lock className="h-5 w-5" style={{ color: 'var(--color-sentinel-blue)' }} />
            </div>
            <div>
              <h3 className="font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>{featureName}</h3>
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                {MODULE_DESCRIPTIONS[module] || module}
              </p>
            </div>
          </div>

          {/* Upgrade message */}
          <div className="mb-6 space-y-3">
            <p className="text-sm leading-relaxed" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              {customMessage || generateUpgradeMessage(module, featureName, savingsData)}
            </p>

            {/* Savings highlights (if data available) */}
            {savingsData && (
              <div className="rounded-lg p-3" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
                <div className="flex justify-between items-baseline gap-4">
                  <div>
                    <p className="text-xs font-medium text-green-400">Estimated Monthly Savings</p>
                    <p className="text-lg font-bold text-green-400">
                      {formatCurrencyZAR(savingsData.savingsZar, 0, 0)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-medium text-green-400">Energy Reduction</p>
                    <p className="text-lg font-bold text-green-400">
                      {formatPercentage(savingsData.savingsPercent, 1)}
                    </p>
                  </div>
                </div>
                <p className="text-xs text-green-400 mt-2">
                  Based on current building conditions • {savingsData.confidence}% confidence
                </p>
              </div>
            )}
          </div>

          {/* Call-to-action buttons */}
          <div className="flex gap-2">
            <button
              onClick={onRequestActivation}
              className="flex-1 px-4 py-2 text-white text-sm font-medium rounded-md hover:opacity-90 transition"
              style={{ background: 'var(--color-sentinel-blue)' }}
            >
              Request Activation
            </button>
            <button
              onClick={() => window.location.href = '/settings/modules'}
              className="flex-1 px-4 py-2 text-sm font-medium rounded-md hover:opacity-80 transition"
              style={{ border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-secondary)' }}
            >
              Learn More
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * Generate context-specific upgrade message based on module and feature
 */
function generateUpgradeMessage(
  module: string,
  featureName: string,
  savingsData?: any
): string {
  const baseMessage = `Enable ${MODULE_DESCRIPTIONS[module] || module} to ${getActionVerb(module)} ${featureName.toLowerCase()}`

  if (savingsData?.savingsZar) {
    const savingsPerDay = Math.round(savingsData.savingsZar / 30)
    return `${baseMessage} and save approximately R${savingsPerDay}/day on operational costs.`
  }

  if (savingsData?.savingsPercent) {
    return `${baseMessage} and reduce energy consumption by ${formatPercentage(savingsData.savingsPercent, 1)}.`
  }

  return `${baseMessage} and optimize your building operations.`
}

/**
 * Get the action verb appropriate for each module
 */
function getActionVerb(module: string): string {
  const verbs: Record<string, string> = {
    hvac_control: 'automatically adjust',
    energy_control: 'optimize and manage',
    lighting_control: 'control scenes and schedules',
    solar_control: 'optimize dispatch',
    maintenance: 'manage and schedule',
    solar: 'optimize',
    lighting: 'control',
    ml: 'AI-predict',
    energy: 'optimize',
    security: 'manage',
  }
  return verbs[module] || 'access'
}

export default LockedFeatureOverlay
