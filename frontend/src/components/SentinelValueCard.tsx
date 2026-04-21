/**
 * SentinelValueCard — Reusable ROI comparison card
 *
 * Shows baseline vs SENTINEL AI performance with horizontal bars,
 * savings percentage, cost reduction, and carbon offset.
 * Used on every building tab to prove SENTINEL's value with live data.
 *
 * Pattern follows EnergyComparisonPanel (2-bar variant).
 */

import type { LucideIcon } from 'lucide-react';
import { TrendingDown, Leaf } from 'lucide-react';

export interface SentinelValueCardProps {
  title: string;
  icon: LucideIcon;
  baseline: {
    label: string;
    value: number;
    unit: string;
    costZar?: number;
  };
  sentinel: {
    label: string;
    value: number;
    unit: string;
    costZar?: number;
  };
  savingsPercent: number;
  carbonSavedKg?: number;
  period: string;
  collecting?: boolean;
}

export function SentinelValueCard({
  title,
  icon: Icon,
  baseline,
  sentinel,
  savingsPercent,
  carbonSavedKg,
  period,
  collecting,
}: SentinelValueCardProps) {
  if (collecting) {
    return (
      <div
        className="rounded-md overflow-hidden"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div
          className="p-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: 'rgba(34, 197, 94, 0.15)' }}>
              <Icon className="h-5 w-5" style={{ color: 'var(--color-sentinel-green)' }} />
            </div>
            <h3 className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              {title}
            </h3>
          </div>
        </div>
        <div className="p-6 flex items-center gap-3">
          <div
            className="h-3 w-3 rounded-full animate-pulse"
            style={{ background: 'var(--color-sentinel-green)' }}
          />
          <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Collecting baseline data &mdash; comparison available after 7 days of telemetry
          </p>
        </div>
      </div>
    );
  }

  const barPercent = baseline.value > 0
    ? Math.max(5, (sentinel.value / baseline.value) * 100)
    : 100;
  const saved = baseline.value - sentinel.value;
  const costSaved = (baseline.costZar ?? 0) - (sentinel.costZar ?? 0);

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: 'rgba(34, 197, 94, 0.15)' }}>
            <Icon className="h-5 w-5" style={{ color: '#22C55E' }} />
          </div>
          <div>
            <h3 className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              {title}
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              {period} consumption comparison
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded font-medium"
          style={{ background: 'rgba(34, 197, 94, 0.15)', color: 'var(--color-sentinel-green)' }}
        >
          {savingsPercent.toFixed(0)}% Savings
        </span>
      </div>

      {/* Comparison Bars */}
      <div className="p-4 space-y-4">
        {/* Baseline bar — gray, 100% */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                <TrendingDown className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {baseline.label}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {baseline.value.toLocaleString()} {baseline.unit}
              </span>
              {baseline.costZar != null && (
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  R{baseline.costZar.toLocaleString()}
                </span>
              )}
            </div>
          </div>
          <div
            className="h-3 rounded-full overflow-hidden"
            style={{ background: 'var(--color-sentinel-bg-secondary)' }}
          >
            <div
              className="h-full transition-all duration-500"
              style={{ width: '100%', background: 'var(--color-sentinel-text-secondary)' }}
            />
          </div>
        </div>

        {/* SENTINEL bar — green, proportional */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div style={{ color: 'var(--color-sentinel-green)' }}>
                <Leaf className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {sentinel.label}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {sentinel.value.toLocaleString()} {sentinel.unit}
              </span>
              {sentinel.costZar != null && (
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  R{sentinel.costZar.toLocaleString()}
                </span>
              )}
              <span
                className="text-xs px-2 py-1 rounded"
                style={{ background: 'rgba(34, 197, 94, 0.15)', color: 'var(--color-sentinel-green)' }}
              >
                -{savingsPercent.toFixed(0)}%
              </span>
            </div>
          </div>
          <div
            className="h-3 rounded-full overflow-hidden"
            style={{ background: 'var(--color-sentinel-bg-secondary)' }}
          >
            <div
              className="h-full transition-all duration-500"
              style={{ width: `${barPercent}%`, background: 'var(--color-sentinel-green)' }}
            />
          </div>
        </div>

        {/* Value Proposition Callout */}
        <div
          className="mt-4 p-3 rounded-lg"
          style={{
            background: 'rgba(34, 197, 94, 0.1)',
            border: '1px solid rgba(34, 197, 94, 0.3)',
          }}
        >
          <div className="flex items-center gap-2">
            <Leaf className="h-5 w-5 flex-shrink-0" style={{ color: 'var(--color-sentinel-green)' }} />
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--color-sentinel-green)' }}>
                SENTINEL AI Optimization
              </p>
              <p className="text-xs" style={{ color: 'var(--color-sentinel-green)', opacity: 0.8 }}>
                {saved.toLocaleString()} {baseline.unit} saved
                {costSaved > 0 && <> &bull; R{costSaved.toLocaleString()} cost reduction</>}
                {carbonSavedKg != null && carbonSavedKg > 0 && (
                  <> &bull; {carbonSavedKg.toLocaleString()} kg CO&#8322; avoided</>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
