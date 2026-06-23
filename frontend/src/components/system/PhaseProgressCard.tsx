/**
 * PhaseProgressCard — Clear visual indicator of where the site is in the
 * onboarding lifecycle and what's needed to advance to the next phase.
 */

import { Shield, ArrowRight, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react';

export interface PhaseProgressProps {
  currentPhase: string | null;
  isLoading?: boolean;
  /** Gates with their status for the current phase */
  gates?: { name: string; passed: boolean; label: string }[];
  /** Whether the current phase is actually eligible for promotion. */
  canPromote?: boolean;
  /** Overall recommendation quality gate status for autonomous authority. */
  qualityGateStatus?: 'pass' | 'warn' | 'fail' | 'na' | null;
  /** Hours since site creation */
  hoursSinceCreated?: number;
  /** Successful bridge polls */
  bridgePolls?: number;
  /** Data quality score 0-1 */
  dataQualityScore?: number;
}

const PHASE_DETAILS: Record<string, { label: string; color: string; next: string; desc: string }> = {
  commissioning: {
    label: 'Commissioning',
    color: '#f59e0b',
    next: 'shadow_live',
    desc: 'System is learning. Data flows at 10% to protect baselines from startup noise.',
  },
  shadow_live: {
    label: 'Shadow Live',
    color: '#3b82f6',
    next: 'advisory',
    desc: 'Data flowing at 50%. Baselines being established. Monitoring data quality.',
  },
  advisory: {
    label: 'Advisory',
    color: '#22c55e',
    next: 'supervised',
    desc: 'Full data flow. Recommendations visible. System is ready for supervised control.',
  },
  supervised: {
    label: 'Supervised',
    color: '#22c55e',
    next: 'automatic',
    desc: 'Control active with human approval. System is trusted for most operations.',
  },
  automatic: {
    label: 'Automatic',
    color: '#22c55e',
    next: '',
    desc: 'Full autonomous operations. System is fully trusted.',
  },
};

function phaseProgress(current: string, gates?: { passed: boolean }[]): number {
  if (!gates || gates.length === 0) return 0;
  const passed = gates.filter(g => g.passed).length;
  return Math.round((passed / gates.length) * 100);
}

export function PhaseProgressCard({
  currentPhase,
  isLoading,
  gates,
  canPromote,
  qualityGateStatus,
  hoursSinceCreated,
}: PhaseProgressProps) {
  const phase = currentPhase || 'commissioning';
  const info = PHASE_DETAILS[phase] || PHASE_DETAILS.commissioning;
  const progress = phaseProgress(phase, gates);
  const isLastPhase = phase === 'automatic';
  const passedCount = gates?.filter(g => g.passed).length ?? 0;
  const totalGates = gates?.length ?? 0;
  const nextPhaseLabel = PHASE_DETAILS[info.next]?.label || info.next;
  const promotionBlocked = progress >= 100 && !isLastPhase && canPromote === false;
  const summaryText = progress < 100
    ? `${passedCount}/${totalGates} gates passed — completing requirements to advance`
    : isLastPhase
    ? 'All phases complete — system at full capability'
    : promotionBlocked && qualityGateStatus === 'fail'
    ? `Data gates passed — Quality Gate still blocks ${nextPhaseLabel}`
    : promotionBlocked
    ? `Data gates passed — promotion readiness still pending for ${nextPhaseLabel}`
    : `All promotion checks passed — ready to advance to ${nextPhaseLabel}`;

  // Determine status color
  const _statusColor = progress >= 100 ? '#22c55e' : progress >= 50 ? '#f59e0b' : '#ef4444';

  if (isLoading) {
    return (
      <div className="glass-panel rounded-lg p-5 flex items-center gap-3" style={{ border: '1px solid var(--glass-border)' }}>
        <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--color-sentinel-blue)' }} />
        <span className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading phase status...</span>
      </div>
    );
  }

  return (
    <div className="glass-panel rounded-lg p-5" style={{ border: '1px solid var(--glass-border)' }}>
      {/* Header: Current Phase with Status Badge */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Shield className="w-5 h-5" style={{ color: info.color }} />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {info.label}
              </span>
              <span
                className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold"
                style={{
                  background: progress >= 100 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                  border: `1px solid ${progress >= 100 ? 'rgba(16, 185, 129, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
                  color: progress >= 100 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
                }}
              >
                {progress}%
              </span>
            </div>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              {info.desc}
            </p>
          </div>
        </div>

        {/* Next phase indicator */}
        {!isLastPhase && (
          <div className="flex items-center gap-2 ml-4">
            <ArrowRight className="w-4 h-4" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
            <span className="text-xs font-medium" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
              {PHASE_DETAILS[info.next]?.label || info.next}
            </span>
          </div>
        )}
      </div>

      {/* Progress Bar */}
      <div className="w-full h-2 rounded-full mb-4" style={{ background: 'var(--color-sentinel-bg-secondary)' }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${progress}%`,
            background: progress >= 100
              ? 'linear-gradient(90deg, #22c55e, #16a34a)'
              : 'linear-gradient(90deg, #f59e0b, #eab308)',
          }}
        />
      </div>

      {/* Gates grid */}
      {gates && gates.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-4">
          {gates.map((gate) => (
            <div
              key={gate.name}
              className="flex items-center gap-2 rounded px-3 py-2 text-xs"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--glass-border)',
                color: gate.passed ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-disabled)',
              }}
            >
              {gate.passed ? (
                <CheckCircle className="w-3.5 h-3.5 shrink-0" />
              ) : (
                <XCircle className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
              )}
              <span style={{ color: gate.passed ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-secondary)' }}>
                {gate.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Summary status */}
      <div
        className="flex items-center justify-between text-xs pt-3"
        style={{ borderTop: '1px solid var(--glass-border)' }}
      >
        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {summaryText}
          </span>
        </div>
        {progress < 100 && hoursSinceCreated !== undefined && (
          <span style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            {hoursSinceCreated.toFixed(0)}h since created
          </span>
        )}
      </div>
    </div>
  );
}

export default PhaseProgressCard;
