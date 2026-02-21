/**
 * CommissioningGatePanel — Phase 108
 *
 * Go/No-Go panel showing commissioning gate status.
 * Shows PASS/FAIL badge, gate grid with icons, consecutive pass days,
 * and promotion readiness.
 * Muted message when commissioning is null (SIMULATION mode).
 */

import { CheckCircle, XCircle, Shield } from 'lucide-react';
import type { CommissioningSnapshot } from '@/lib/api/system';

interface CommissioningGatePanelProps {
  commissioning: CommissioningSnapshot | null;
}

const GATE_LABELS: Record<string, string> = {
  match_coverage: 'Match Coverage',
  unmatched_points: 'Unmatched Points',
  data_freshness: 'Data Freshness',
  error_rate: 'Error Rate',
  duplicate_rate: 'Duplicate Rate',
  source_provenance: 'Source Provenance',
  value_validity: 'Value Validity',
  timestamp_integrity: 'Timestamp Integrity',
};

export function CommissioningGatePanel({ commissioning }: CommissioningGatePanelProps) {
  if (!commissioning) {
    return (
      <div
        className="glass-panel rounded-lg p-5"
        style={{ border: '1px solid var(--glass-border)' }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Shield className="w-5 h-5" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
          <span
            className="text-xs uppercase tracking-wider font-medium"
            style={{ color: 'var(--color-sentinel-text-disabled)' }}
          >
            Commissioning Gates
          </span>
        </div>
        <p
          className="text-sm"
          style={{ color: 'var(--color-sentinel-text-disabled)' }}
        >
          Not applicable in SIMULATION mode. Switch to SHADOW_LIVE to begin commissioning.
        </p>
      </div>
    );
  }

  const allPassed = commissioning.all_gates_passed;
  const passedGates = new Set(
    // blocking_gates lists the FAILED gates; invert to get passed
    Object.keys(GATE_LABELS).filter(g => !commissioning.blocking_gates.includes(g))
  );

  return (
    <div
      className="glass-panel rounded-lg p-5"
      style={{ border: '1px solid var(--glass-border)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5" style={{ color: 'var(--color-sentinel-blue)' }} />
          <span
            className="text-xs uppercase tracking-wider font-medium"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Commissioning Gates
          </span>
        </div>
        <span
          className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold"
          style={{
            background: allPassed ? 'rgba(16, 185, 129, 0.15)' : 'rgba(220, 38, 38, 0.15)',
            border: `1px solid ${allPassed ? 'rgba(16, 185, 129, 0.35)' : 'rgba(220, 38, 38, 0.35)'}`,
            color: allPassed ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-red)',
          }}
        >
          {allPassed ? 'GO' : 'NO-GO'}
        </span>
      </div>

      {/* Gate Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        {Object.entries(GATE_LABELS).map(([id, label]) => {
          const passed = passedGates.has(id);
          return (
            <div
              key={id}
              className="flex items-center gap-2 rounded px-2.5 py-2 text-xs"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--glass-border)',
                color: passed ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-red)',
              }}
            >
              {passed ? (
                <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
              ) : (
                <XCircle className="w-3.5 h-3.5 flex-shrink-0" />
              )}
              <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>{label}</span>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between text-xs pt-3"
        style={{ borderTop: '1px solid var(--glass-border)' }}
      >
        <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          {commissioning.gates_passed}/{commissioning.gates_total} gates passed
          {' · '}
          {commissioning.consecutive_pass_days} consecutive day(s)
        </span>
        <span
          className="font-medium"
          style={{
            color: commissioning.can_promote
              ? 'var(--color-sentinel-green)'
              : 'var(--color-sentinel-text-disabled)',
          }}
        >
          {commissioning.can_promote ? 'Ready to promote' : 'Not ready'}
        </span>
      </div>
    </div>
  );
}

export default CommissioningGatePanel;
