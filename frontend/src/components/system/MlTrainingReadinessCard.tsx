/**
 * MlTrainingReadinessCard — Phase 236
 *
 * Displays whether a site is ready to enable ML training.
 * Checks telemetry-only quality metrics (freshness, coverage, error rate,
 * manual sources, unmatched points, commissioning gates, consecutive days).
 * Feedback-loop metrics are excluded because they depend on ML already running.
 */

import { CheckCircle, XCircle, Shield, BrainCircuit, AlertTriangle } from 'lucide-react';
import type { MlTrainingReadiness } from '@/lib/api/system';

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const METRIC_LABELS: Record<string, string> = {
  freshness_minutes: 'Freshness',
  ingest_error_rate_pct_1h: 'Error Rate',
  match_coverage_pct: 'Match Coverage',
  manual_source_pct: 'Manual Sources',
  unmatched_points_pct: 'Unmatched Points',
  commissioning_all_gates_passed: 'Gates Passed',
  consecutive_pass_days: 'Consecutive Days',
};

const LOWER_IS_BETTER = new Set([
  'freshness_minutes',
  'ingest_error_rate_pct_1h',
  'manual_source_pct',
  'unmatched_points_pct',
]);

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function fmt(metric: string, value: number | null): string {
  if (value === null || value === undefined) return 'N/A';
  if (metric === 'freshness_minutes') return `${value.toFixed(0)}m`;
  if (metric === 'consecutive_pass_days') return `${value.toFixed(0)}d`;
  if (metric.includes('pct') || metric.includes('rate') || metric.includes('coverage')) {
    return `${value.toFixed(1)}%`;
  }
  return `${value}`;
}

function tone(state: string): 'green' | 'orange' | 'red' | 'gray' {
  switch (state) {
    case 'pass': return 'green';
    case 'warn': return 'orange';
    case 'fail': return 'red';
    default:     return 'gray';
  }
}

function colorVar(c: 'green' | 'orange' | 'red' | 'gray'): string {
  if (c === 'green') return 'var(--color-sentinel-green)';
  if (c === 'orange') return 'var(--color-sentinel-orange)';
  if (c === 'red') return 'var(--color-sentinel-red)';
  return 'var(--color-sentinel-text-disabled)';
}

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

interface Props {
  readiness: MlTrainingReadiness | null;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function MlTrainingReadinessCard({ readiness }: Props) {
  if (!readiness) {
    return (
      <div
        className="flex items-center gap-2 text-xs rounded px-3 py-2"
        style={{
          background: 'var(--color-sentinel-bg-secondary)',
          border: '1px solid var(--glass-border)',
          color: 'var(--color-sentinel-text-disabled)',
        }}
      >
        <Shield className="w-4 h-4" />
        <span>ML training readiness data is not available yet.</span>
      </div>
    );
  }

  const overall = readiness.overall;
  const isReady = readiness.ready;
  const isFail = overall === 'fail';
  const isWarn = overall === 'warn';
  const isPass = overall === 'pass';
  const blocking = readiness.blocking_metrics;
  const results = readiness.telemetry_results ?? [];

  return (
    <div
      className="glass-panel rounded-lg p-5"
      style={{ border: '1px solid var(--glass-border)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-5 h-5" style={{ color: 'var(--color-sentinel-blue)' }} />
          <span
            className="text-xs uppercase tracking-wider font-medium"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            ML Training Readiness
          </span>
        </div>
        <span
          className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold"
          style={{
            background: isReady
              ? 'rgba(16, 185, 129, 0.15)'
              : isWarn
              ? 'rgba(245, 158, 11, 0.15)'
              : 'rgba(220, 38, 38, 0.15)',
            border: `1px solid ${
              isReady
                ? 'rgba(16, 185, 129, 0.35)'
                : isWarn
                ? 'rgba(245, 158, 11, 0.35)'
                : 'rgba(220, 38, 38, 0.35)'
            }`,
            color: isReady
              ? 'var(--color-sentinel-green)'
              : isWarn
              ? 'var(--color-sentinel-orange)'
              : 'var(--color-sentinel-red)',
          }}
        >
          {isReady ? 'READY' : isFail ? 'BLOCKED' : isWarn ? 'NOT READY' : 'UNKNOWN'}
        </span>
      </div>

      {/* Blocking metrics banner */}
      {blocking.length > 0 && (
        <div
          className="rounded px-3 py-2 mb-3 text-xs"
          style={{
            background: 'rgba(220, 38, 38, 0.08)',
            border: '1px solid rgba(220, 38, 38, 0.30)',
            color: 'var(--color-sentinel-text-secondary)',
          }}
        >
          <span className="font-semibold" style={{ color: 'var(--color-sentinel-red)' }}>
            Blocking metrics:
          </span>{' '}
          {blocking.map((m, i) => (
            <span key={m}>
              {i > 0 && '; '}
              {METRIC_LABELS[m] ?? m}
            </span>
          ))}
        </div>
      )}

      {/* Telemetry metrics grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        {results.map((rule) => {
          const c = tone(rule.state);
          return (
            <div
              key={rule.metric}
              className="flex items-center gap-2 rounded px-2.5 py-2 text-xs"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--glass-border)',
                color: colorVar(c),
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
                {METRIC_LABELS[rule.metric] ?? rule.metric}
              </span>
              <span className="ml-auto font-medium">
                {fmt(rule.metric, rule.value)}
              </span>
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
          {results.filter((r) => r.state === 'pass').length}/{results.filter((r) => r.state !== 'na').length} metrics passing
        </span>
        {readiness.evaluated_at && (
          <span style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            Evaluated {new Date(readiness.evaluated_at).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  );
}

export default MlTrainingReadinessCard;
