/**
 * AdvisoryLockedOverlay - Deployment-mode gating for interactive controls
 *
 * Locks controls when the site is in advisory mode, showing a message
 * that promotion to Supervised is required before controls become active.
 * Read-only telemetry, status displays, and dashboards remain visible.
 *
 * Usage:
 * <AdvisoryLockedOverlay isAdvisory={onboardingPhase === 'advisory'}>
 *   <ChillerControlPanel />
 * </AdvisoryLockedOverlay>
 */

import type { ReactNode } from 'react'
import { Lock, ArrowUp } from 'lucide-react'

interface AdvisoryLockedOverlayProps {
  isAdvisory: boolean
  children: ReactNode
  featureName?: string
}

export function AdvisoryLockedOverlay({
  isAdvisory,
  children,
  featureName = 'Controls',
}: AdvisoryLockedOverlayProps) {
  if (!isAdvisory) {
    return <>{children}</>
  }

  return (
    <div className="relative">
      {/* Greyed-out child component */}
      <div className="opacity-30 pointer-events-none select-none">
        {children}
      </div>

      {/* Advisory mode locked overlay */}
      <div className="absolute inset-0 flex items-center justify-center z-10">
        <div
          className="rounded-md p-5 max-w-sm mx-4 text-center"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <div className="flex justify-center mb-3">
            <div
              className="p-2 rounded-lg"
              style={{ background: 'rgba(245, 158, 11, 0.15)' }}
            >
              <Lock className="h-5 w-5" style={{ color: 'var(--color-sentinel-amber)' }} />
            </div>
          </div>
          <h3
            className="font-semibold text-sm mb-1"
            style={{ color: 'var(--color-sentinel-text-primary)' }}
          >
            {featureName} Locked
          </h3>
          <p
            className="text-xs leading-relaxed mb-3"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Controls are disabled in Advisory mode. Promote this site to
            Supervised mode to enable interactive control.
          </p>
          <div className="flex items-center justify-center gap-1.5 text-xs font-medium" style={{ color: 'var(--color-sentinel-amber)' }}>
            <ArrowUp className="w-3.5 h-3.5" />
            Settings &gt; Onboarding Phase &gt; Supervised
          </div>
        </div>
      </div>
    </div>
  )
}

export default AdvisoryLockedOverlay
