// @ts-nocheck
/**
 * Shared components for Intelligence Cards — three-state display pattern.
 *
 * State 1: NO DATA — BMS/simulator offline. Compact card, no metrics.
 * State 2: LEARNING — Data flowing but insufficient for comparison.
 * State 3: ACTIVE — Enough data for value display.
 */

import { ArrowRight } from 'lucide-react';

export { formatCurrencyZAR } from '@/lib/locale';

/** Card display state */
export type CardState = 'no-data' | 'learning' | 'active';

/** Check if a value is meaningful (non-zero, non-null, non-undefined) */
export function hasValue(v: unknown): boolean {
  if (v === null || v === undefined) return false;
  if (typeof v === 'number') return v !== 0 && !isNaN(v);
  if (typeof v === 'string') return v.length > 0;
  return true;
}

/** Reusable metric box for intelligence cards */
export function ValueMetricBox({
  label,
  value,
  subtitle,
  color,
}: {
  label: string;
  value: string;
  subtitle?: string;
  color: string;
}) {
  return (
    <div
      className="p-3 rounded text-center"
      style={{
        background: 'var(--color-sentinel-bg-secondary)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      <div className="text-lg font-semibold" style={{ color }}>
        {value}
      </div>
      {subtitle && (
        <div
          className="text-[10px] mt-0.5"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          {subtitle}
        </div>
      )}
      <div
        className="text-xs mt-1"
        style={{ color: 'var(--color-sentinel-text-secondary)' }}
      >
        {label}
      </div>
    </div>
  );
}

/** State 1: Awaiting data badge — muted blue */
export function AwaitingDataBadge() {
  return (
    <span
      className="text-xs px-2 py-1 rounded font-medium"
      style={{
        background: 'rgba(59, 130, 246, 0.12)',
        color: 'var(--color-sentinel-blue)',
      }}
    >
      Awaiting data
    </span>
  );
}

/** State 2: Learning badge — blue with pulse */
export function LearningBadge({ text = 'Learning' }: { text?: string }) {
  return (
    <span
      className="text-xs px-2 py-1 rounded font-medium animate-pulse"
      style={{
        background: 'rgba(59, 130, 246, 0.12)',
        color: 'var(--color-sentinel-blue)',
      }}
    >
      {text}
    </span>
  );
}

/** State 3: Active value badge — green (positive) or amber (attention) */
export function ValueBadge({
  text,
  positive = true,
}: {
  text: string;
  positive?: boolean;
}) {
  return (
    <span
      className="text-xs px-2 py-1 rounded font-medium"
      style={{
        background: positive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
        color: positive ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
      }}
    >
      {text}
    </span>
  );
}

/** Backwards compat alias */
export const FallbackBadge = LearningBadge;

/**
 * Baseline vs SENTINEL comparison bar.
 * Shows two horizontal bars: "Current Baseline" and "With SENTINEL",
 * with the savings amount and percentage highlighted.
 */
export function BaselineComparisonBar({
  baselineValue,
  optimizedValue,
  unit = '',
  baselineLabel = 'Current Baseline',
  optimizedLabel = 'With SENTINEL',
  accentColor = 'var(--color-sentinel-green)',
}: {
  baselineValue: number;
  optimizedValue: number;
  unit?: string;
  baselineLabel?: string;
  optimizedLabel?: string;
  accentColor?: string;
}) {
  if (baselineValue <= 0) return null;
  const savings = baselineValue - optimizedValue;
  const savingsPct = Math.round((savings / baselineValue) * 100);
  const optimizedPct = Math.max(5, Math.round((optimizedValue / baselineValue) * 100));
  const formatVal = (v: number) =>
    unit === 'ZAR'
      ? formatCurrencyZAR(v)
      : `${v.toLocaleString('en-ZA', { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`;

  return (
    <div className="space-y-2">
      {/* Baseline bar — full width, muted */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px]" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {baselineLabel}
          </span>
          <span className="text-[11px] font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {formatVal(baselineValue)}
          </span>
        </div>
        <div
          className="h-5 rounded"
          style={{
            background: 'var(--color-sentinel-bg-secondary)',
            border: '1px solid var(--color-sentinel-border)',
            width: '100%',
          }}
        />
      </div>
      {/* Optimized bar — shorter, accent colored, with savings callout */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] font-medium" style={{ color: accentColor }}>
            {optimizedLabel}
          </span>
          <span className="text-[11px] font-medium" style={{ color: accentColor }}>
            {formatVal(optimizedValue)}
            <span
              className="ml-2 px-1.5 py-0.5 rounded text-[10px]"
              style={{ background: `${accentColor}22`, color: accentColor }}
            >
              ↓ {savingsPct}% saved
            </span>
          </span>
        </div>
        <div className="relative h-5 rounded overflow-hidden" style={{ width: '100%' }}>
          <div
            className="absolute inset-y-0 left-0 rounded"
            style={{
              width: `${optimizedPct}%`,
              background: accentColor,
              opacity: 0.7,
            }}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Complete card shell for all three states.
 * State 1 (no-data): compact — icon, title, badge, footer. No metrics.
 * State 2 (learning): shows metrics if provided, pulse badge.
 * State 3 (active): full metrics + value badge.
 */
export function IntelligenceCard({
  title,
  subtitle,
  icon,
  iconBg,
  accentColor,
  badge,
  metrics,
  comparison,
  footer,
  state,
  onNavigate,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  iconBg: string;
  accentColor: string;
  badge: React.ReactNode;
  metrics?: React.ReactNode;
  comparison?: React.ReactNode;
  footer: string;
  state: CardState;
  onNavigate?: () => void;
}) {
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: state === 'no-data' ? 'none' : '1px solid var(--color-sentinel-border)' }}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: iconBg }}>
            {icon}
          </div>
          <div>
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              {title}
            </h3>
            <span
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              {subtitle}
            </span>
          </div>
        </div>
        {badge}
      </div>

      {/* Metrics — only shown when active data available */}
      {state === 'active' && metrics && (
        <div className="px-4 pt-4">
          <div className="grid grid-cols-3 gap-3">{metrics}</div>
        </div>
      )}

      {/* Baseline vs SENTINEL comparison — only shown when active */}
      {state === 'active' && comparison && (
        <div className="px-4 pt-3">
          {comparison}
        </div>
      )}

      {/* AI Footer + Navigate — shown for learning and active */}
      {state !== 'no-data' && (
        <div className="px-4 py-4">
          <div className="flex items-center justify-between">
            <p
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              <span style={{ color: accentColor }}>SENTINEL AI:</span> {footer}
            </p>
            {onNavigate && (
              <button
                onClick={onNavigate}
                className="flex items-center gap-1 text-xs font-medium hover:underline"
                style={{
                  color: accentColor,
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                View Details <ArrowRight className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* No-data footer — compact inline */}
      {state === 'no-data' && (
        <div className="px-4 pb-4">
          <p
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            <span style={{ color: accentColor }}>SENTINEL AI:</span> {footer}
          </p>
        </div>
      )}
    </div>
  );
}
