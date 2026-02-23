/**
 * TechnicianPortalGated - Module-gated technician work order portal
 *
 * Wraps TechnicianPortal with LockedFeatureOverlay to gate behind MAINTENANCE module.
 * Shows technician dashboard with work orders, approvals, and order history when active.
 * When inactive, displays upgrade prompt with maintenance automation savings.
 *
 * Usage:
 * <TechnicianPortalGated />  // With gating
 * <TechnicianPortalGated gated={false} />  // Bypass gating
 */

import TechnicianPortal from './TechnicianPortal'
import { LockedFeatureOverlay } from './LockedFeatureOverlay'

interface TechnicianPortalGatedProps {
  /** Whether to apply module gating (default: true) */
  gated?: boolean
}

export function TechnicianPortalGated({ gated = true }: TechnicianPortalGatedProps) {
  if (!gated) {
    // Bypass gating for backward compatibility
    return <TechnicianPortal />
  }

  return (
    <LockedFeatureOverlay
      module="maintenance"
      featureName="Technician Portal"
      customMessage="Enable Maintenance module to let SENTINEL automatically create, assign, and track work orders for equipment issues — reduce mean time to repair (MTTR) by 40% and improve first-time fix rates."
      renderPreviewWhenLocked={false}
    >
      <TechnicianPortal />
    </LockedFeatureOverlay>
  )
}

export default TechnicianPortalGated
