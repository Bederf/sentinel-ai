/**
 * AdvisoryModeGuide: Step-by-Step BMS Execution Instructions
 *
 * Renders a four-section advisory guide that helps operators understand
 * and verify BMS navigation paths before executing commands.
 *
 * Phase 172-02-03: Hardened advisory mode rendering
 */

import type { BmsExecutionGuide } from '@/lib/decisionSurface'
import { NavigationPathSection } from './advisory/NavigationPathSection'
import { OperatorActionSection } from './advisory/OperatorActionSection'
import { VerificationSection } from './advisory/VerificationSection'
import { SafetyNoticeSection } from './advisory/SafetyNoticeSection'
import { FooterConfirmation } from './advisory/FooterConfirmation'

interface AdvisoryModeGuideProps {
  bmsGuide: BmsExecutionGuide | null
  _actionSummary: string // Used for future extensions
  primaryMetric: string
}

/**
 * Determine if escalation is needed based on equipment type
 */
function getEscalationNote(assetId: string | null): string | null {
  if (!assetId) return null

  const type = assetId.split('-')[1]?.toUpperCase()
  if (type === 'FIRE') {
    return 'Contact FM/Safety team immediately if manual intervention is required.'
  }
  if (type === 'CT') {
    return 'Escalate load balancing to the electrician if action is required.'
  }
  if (type === 'ACC') {
    return 'Coordinate with security team before making any access control changes.'
  }
  if (type === 'CCTV') {
    return 'Coordinate with security team if camera reset or repositioning is needed.'
  }

  return null
}

export function AdvisoryModeGuide({
  bmsGuide,
  _actionSummary,
  primaryMetric,
}: AdvisoryModeGuideProps) {
  const escalationNote = getEscalationNote(bmsGuide?.assetId ?? null)

  return (
    <div className="space-y-4">
      <NavigationPathSection navigationPath={bmsGuide?.navigationPath ?? null} />
      <OperatorActionSection bmsGuide={bmsGuide} />
      <VerificationSection bmsGuide={bmsGuide} primaryMetric={primaryMetric} />
      {escalationNote && <SafetyNoticeSection message={escalationNote} />}
      <FooterConfirmation />
    </div>
  )
}
