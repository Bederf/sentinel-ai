/**
 * CommissioningGatePanel — Phase 108 / 109
 *
 * Go/No-Go panel showing commissioning gate status AND quality gate metrics.
 * Section 1: 8 commissioning scorecard gates + consecutive pass days + can_promote
 * Section 2: 14 quality gate metrics with pass/warn/fail state + enforcement action
 *
 * Commissioning gates are pass/fail based on site scorecard.
 * Quality gate metrics are evaluated against thresholds per ingestion mode.
 */

import { CheckCircle, XCircle, Shield, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { CommissioningSnapshot, QualityGateStatus } from '@/lib/api/system';

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

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

const QUALITY_GATE_LABELS: Record<string, string> = {
  freshness_minutes: 'Freshness',
  ingest_error_rate_pct_1h: 'Error Rate',
  match_coverage_pct: 'Match Coverage',
  manual_source_pct: 'Manual Sources',
  unmatched_points_pct: 'Unmatched Points',
  commissioning_all_gates_passed: 'Gates Passed',
  truth_check_pass_rate_pct: 'Truth Check',
  consecutive_pass_days: 'Consecutive Days',
  mv_accuracy_7d_pct: 'MV Accuracy',
  comfort_violation_rate_7d_pct: 'Comfort Violations',
  rollback_rate_7d_pct: 'Rollback Rate',
  feedback_capture_rate_7d_pct: 'Feedback Capture',
  label_lag_p95_hours: 'Label Lag',
  drift_critical_alerts_24h: 'Drift Alerts',
};

const ENFORCEMENT_LABELS: Record<string, string> = {
  normal: 'Normal — no additional gate action',
  cap_confidence: 'Confidence Capped — reduced autonomous authority',
  suppress_tier3: 'Tier3 Suppressed — pending approval required',
  block_writes: 'Write Blocked — log-only mode active',
};

const LOWER_IS_BETTER_METRICS = new Set([
  'freshness_minutes',
  'ingest_error_rate_pct_1h',
  'manual_source_pct',
  'unmatched_points_pct',
  'comfort_violation_rate_7d_pct',
  'rollback_rate_7d_pct',
  'label_lag_p95_hours',
  'drift_critical_alerts_24h',
]);

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatValue(metric: string, value: number | null): string {
  if (value === null || value === undefined) return 'N/A';
  if (metric === 'freshness_minutes') return `${value.toFixed(0)}m`;
  if (metric === 'label_lag_p95_hours') return `${value.toFixed(1)}h`;
  if (metric.includes('pct') || metric.includes('rate') || metric.includes('coverage')) {
    return `${value.toFixed(1)}%`;
  }
  if (metric.includes('accuracy')) return `${value.toFixed(1)}%`;
  if (metric === 'consecutive_pass_days') return `${value.toFixed(0)}d`;
  return `${value}`;
}

function stateColor(state: string): 'green' | 'orange' | 'red' | 'gray' {
  switch (state) {
    case 'pass': return 'green';
    case 'warn': return 'orange';
    case 'fail': return 'red';
    default:     return 'gray';
  }
}

function enforcementColor(action: string): 'green' | 'orange' | 'red' | 'purple' | 'gray' {
  switch (action) {
    case 'normal':          return 'green';
    case 'cap_confidence':  return 'orange';
    case 'suppress_tier3':  return 'orange';
    case 'block_writes':    return 'red';
    default:               return 'gray';
  }
}

function ruleThresholdText(rule: { metric: string; pass_bound: number | null }): string | null {
  if (rule.pass_bound === null || rule.pass_bound === undefined) return null;
  const operator = LOWER_IS_BETTER_METRICS.has(rule.metric) ? '<=' : '>=';
  return `needs ${operator} ${formatValue(rule.metric, rule.pass_bound)}`;
}

function metricTone(color: 'green' | 'orange' | 'red' | 'gray'): string {
  if (color === 'green') return 'var(--color-sentinel-green)';
  if (color === 'orange') return 'var(--color-sentinel-orange)';
  if (color === 'red') return 'var(--color-sentinel-red)';
  return 'var(--color-sentinel-text-disabled)';
}

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

interface CommissioningGatePanelProps {
  commissioning: CommissioningSnapshot | null;
  qualityGate?: QualityGateStatus | null;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function CommissioningGatePanel({ commissioning, qualityGate }: CommissioningGatePanelProps) {
  const [qgExpanded, setQgExpanded] = useState(false);

  useEffect(() => {
    if (qualityGate?.overall_status === 'fail') {
      setQgExpanded(true);
    }
  }, [qualityGate?.overall_status]);

  // ----- Commissioning -----

  const allPassed = commissioning?.all_gates_passed ?? false;
  const passedGates = new Set(
    commissioning
      ? Object.keys(GATE_LABELS).filter(g => !commissioning.blocking_gates.includes(g))
      : []
  );

  // ----- Quality Gate -----

  const qgOverall = qualityGate?.overall_status ?? 'na';
  const qgEnforcement = qualityGate?.enforcement_action ?? 'unknown';

  const failedRuleResults = (qualityGate?.rule_results ?? []).filter(r => r.state === 'fail');
  const warnRuleResults = (qualityGate?.rule_results ?? []).filter(r => r.state === 'warn');
  const failedCount = qualityGate?.failed_rules?.length
    ? qualityGate.failed_rules.length
    : failedRuleResults.length;
  const warnCount = qualityGate?.warn_rules?.length
    ? qualityGate.warn_rules.length
    : warnRuleResults.length;
  const qgPassCount = (qualityGate?.rule_results ?? []).filter(r => r.state === 'pass').length;
  const qgTotal = (qualityGate?.rule_results ?? []).filter(r => r.state !== 'na').length;

  const _isQgFail = qgOverall === 'fail';
  const isQgWarn = qgOverall === 'warn';
  const isQgPass = qgOverall === 'pass';

  return (
    <div
      className="glass-panel rounded-lg p-5"
      style={{ border: '1px solid var(--glass-border)' }}
    >
      {/* ================================================================
          SECTION 1: Commissioning Gates
          ================================================================ */}
      {commissioning ? (
        <div className="mb-5">
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
            {commissioning?.gates_passed ?? 0}/{commissioning?.gates_total ?? 8} gates passed
            {' · '}
            {commissioning?.consecutive_pass_days ?? 0} consecutive day(s)
            {commissioning?.stage_calendar_days != null && (
              <> · {commissioning.stage_calendar_days}d in stage</>
            )}
          </span>
          <span
            className="font-medium"
            style={{
              color: commissioning?.can_promote
                ? 'var(--color-sentinel-green)'
                : 'var(--color-sentinel-text-disabled)',
            }}
          >
            {commissioning?.can_promote ? 'Ready to promote' : 'Not ready'}
          </span>
        </div>
      </div>
      ) : (
        <div
          className="flex items-center gap-2 text-xs rounded px-3 py-2 mb-5"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--glass-border)',
            color: 'var(--color-sentinel-text-disabled)',
          }}
        >
          <Shield className="w-4 h-4" />
          <span>Commissioning data is not available yet.</span>
        </div>
      )}

      {/* ================================================================
          SECTION 2: Quality Gate Metrics
          ================================================================ */}
      {qualityGate ? (
        <div>
          {/* Divider */}
          <div style={{ borderTop: '1px solid var(--glass-border)', marginBottom: '1rem' }} />

          {/* Collapsible header */}
          <button
            onClick={() => setQgExpanded(v => !v)}
            className="w-full flex items-center justify-between mb-3 cursor-pointer bg-transparent border-0 p-0"
          >
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5" style={{ color: 'var(--color-sentinel-blue)' }} />
              <span
                className="text-xs uppercase tracking-wider font-medium"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Quality Gate
              </span>
              {/* Badge: pass/warn/fail */}
              <span
                className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold"
                style={{
                  background:
                    isQgPass ? 'rgba(16, 185, 129, 0.15)' :
                    isQgWarn ? 'rgba(245, 158, 11, 0.15)' :
                    'rgba(220, 38, 38, 0.15)',
                  border: `1px solid ${
                    isQgPass ? 'rgba(16, 185, 129, 0.35)' :
                    isQgWarn ? 'rgba(245, 158, 11, 0.35)' :
                    'rgba(220, 38, 38, 0.35)'
                  }`,
                  color:
                    isQgPass ? 'var(--color-sentinel-green)' :
                    isQgWarn ? 'var(--color-sentinel-orange)' :
                    'var(--color-sentinel-red)',
                }}
              >
                {qgOverall.toUpperCase()}
              </span>
              {/* Failure count */}
              {failedCount > 0 && (
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                  {failedCount} failed
                </span>
              )}
              {warnCount > 0 && (
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                  {warnCount} warn
                </span>
              )}
            </div>
            {qgExpanded
              ? <ChevronDown className="w-4 h-4" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
              : <ChevronRight className="w-4 h-4" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
            }
          </button>

          {/* Expandable body */}
          {qgExpanded && (
            <>
              {/* Enforcement action row */}
              <div
                className="flex items-center gap-2 rounded px-3 py-2 mb-3 text-xs"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  border: `1px solid var(--glass-border)`,
                  color: enforcementColor(qgEnforcement) === 'red'
                    ? 'var(--color-sentinel-red)'
                    : enforcementColor(qgEnforcement) === 'orange'
                    ? 'var(--color-sentinel-orange)'
                    : 'var(--color-sentinel-green)',
                }}
              >
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>
                  <strong>Enforcement: </strong>
                  {ENFORCEMENT_LABELS[qgEnforcement] ?? qgEnforcement}
                </span>
              </div>

              {failedRuleResults.length > 0 && (
                <div
                  className="rounded px-3 py-2 mb-3 text-xs"
                  style={{
                    background: 'rgba(220, 38, 38, 0.08)',
                    border: '1px solid rgba(220, 38, 38, 0.30)',
                    color: 'var(--color-sentinel-text-secondary)',
                  }}
                >
                  <span className="font-semibold" style={{ color: 'var(--color-sentinel-red)' }}>
                    Blocking quality metrics:
                  </span>{' '}
                  {failedRuleResults.map((rule, index) => {
                    const threshold = ruleThresholdText(rule);
                    return (
                      <span key={rule.metric}>
                        {index > 0 && '; '}
                        {QUALITY_GATE_LABELS[rule.metric] ?? rule.metric} {formatValue(rule.metric, rule.value)}
                        {threshold ? ` (${threshold})` : ''}
                      </span>
                    );
                  })}
                </div>
              )}

              {/* Metrics grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
                {(qualityGate.rule_results ?? []).map((rule) => {
                  const color = stateColor(rule.state);
                  return (
                    <div
                      key={rule.metric}
                      className="flex items-center gap-2 rounded px-2.5 py-2 text-xs"
                      style={{
                        background: 'var(--color-sentinel-bg-secondary)',
                        border: '1px solid var(--glass-border)',
                        color: metricTone(color),
                      }}
                    >
                      {rule.state === 'pass' ? (
                        <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
                      ) : rule.state === 'warn' ? (
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                      ) : rule.state === 'na' ? (
                        <Shield className="w-3.5 h-3.5 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 flex-shrink-0" />
                      )}
                      <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                        {QUALITY_GATE_LABELS[rule.metric] ?? rule.metric}
                      </span>
                      <span className="ml-auto font-medium">
                        {formatValue(rule.metric, rule.value)}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Summary footer */}
              <div
                className="flex items-center justify-between text-xs pt-3"
                style={{ borderTop: '1px solid var(--glass-border)' }}
              >
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  {qgPassCount}/{qgTotal} metrics passing · mode: {qualityGate.mode}
                </span>
                {failedCount > 0 && (
                  <span style={{ color: 'var(--color-sentinel-red)' }}>
                    {failedCount} blocking rule{failedCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      ) : (
        /* Quality gate section hidden when no data */
        <div
          className="flex items-center gap-2 text-xs rounded px-3 py-2"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--glass-border)',
            color: 'var(--color-sentinel-text-disabled)',
          }}
        >
          <Shield className="w-4 h-4" />
          <span>Quality gate data is not available yet.</span>
        </div>
      )}
    </div>
  );
}

export default CommissioningGatePanel;
