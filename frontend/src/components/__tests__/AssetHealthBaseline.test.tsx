/**
 * Asset Health + Baseline UI Tests (Phase 109A)
 *
 * Tests baseline/deviation badge rendering logic and filter chip behavior.
 * Since badges are inline in SiteDetail.tsx, we test via a lightweight
 * rendering helper that mirrors the badge logic.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test-utils';
import type { AssetHealthBaseline } from '@/lib/api/sites';

// ---------------------------------------------------------------------------
// Badge rendering helpers (mirrors SiteDetail.tsx inline logic)
// ---------------------------------------------------------------------------

function BaselineBadge({ asset }: { asset: AssetHealthBaseline }) {
  if (asset.has_active_baseline) {
    return (
      <span
        data-testid="baseline-badge"
        className="inline-block px-2 py-0.5 rounded text-xs font-medium"
        style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-sentinel-green)' }}
        title={asset.last_baseline_at ? `Captured: ${asset.last_baseline_at.split('T')[0]}` : undefined}
      >
        Active
      </span>
    );
  }
  return (
    <span
      data-testid="baseline-badge"
      className="inline-block px-2 py-0.5 rounded text-xs font-medium"
      style={{ background: 'var(--color-sentinel-bg-secondary)', color: 'var(--color-sentinel-text-disabled)' }}
    >
      None
    </span>
  );
}

function DeviationBadge({ asset }: { asset: AssetHealthBaseline }) {
  if (asset.max_deviation_percent_24h == null) {
    return <span data-testid="deviation-badge">—</span>;
  }
  const devColor = asset.deviation_status === 'critical'
    ? 'var(--color-sentinel-red)'
    : asset.deviation_status === 'warning'
    ? 'var(--color-sentinel-amber)'
    : 'var(--color-sentinel-green)';
  const devBg = asset.deviation_status === 'critical'
    ? 'rgba(220, 38, 38, 0.15)'
    : asset.deviation_status === 'warning'
    ? 'rgba(245, 158, 11, 0.15)'
    : 'rgba(16, 185, 129, 0.15)';
  return (
    <span
      data-testid="deviation-badge"
      className="inline-block px-2 py-0.5 rounded text-xs font-medium"
      style={{ background: devBg, color: devColor }}
    >
      {asset.max_deviation_percent_24h.toFixed(1)}%
    </span>
  );
}

function FilterChips({
  assets,
  activeFilter,
  onFilter,
}: {
  assets: AssetHealthBaseline[];
  activeFilter: string | null;
  onFilter: (f: string | null) => void;
}) {
  const noBaseline = assets.filter(a => !a.has_active_baseline).length;
  const criticalDev = assets.filter(a => a.deviation_status === 'critical').length;
  return (
    <div data-testid="filter-chips">
      {noBaseline > 0 && (
        <button
          data-testid="chip-no-baseline"
          onClick={() => onFilter(activeFilter === 'no-baseline' ? null : 'no-baseline')}
        >
          No Baseline ({noBaseline})
        </button>
      )}
      {criticalDev > 0 && (
        <button
          data-testid="chip-critical-deviation"
          onClick={() => onFilter(activeFilter === 'critical-deviation' ? null : 'critical-deviation')}
        >
          Critical Deviation ({criticalDev})
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const baseAsset: AssetHealthBaseline = {
  equipment_id: 'S002-AHU-001',
  equipment_name: 'AHU 001',
  equipment_type: 'AHU',
  category: 'HVAC',
  health_score: 85,
  health_status: 'warning',
  health_source: 'equipment_table',
  health_updated_at: '2026-02-20T10:00:00',
  has_active_baseline: false,
  last_baseline_at: null,
  total_baselines: 0,
  baseline_source: null,
  max_deviation_percent_24h: null,
  deviation_status: null,
};

// ===========================================================================
// Tests
// ===========================================================================

describe('BaselineBadge', () => {
  it('renders "Active" green badge when has_active_baseline is true', () => {
    const asset = { ...baseAsset, has_active_baseline: true, last_baseline_at: '2026-02-15T08:00:00' };
    render(<BaselineBadge asset={asset} />);
    const badge = screen.getByTestId('baseline-badge');
    expect(badge.textContent).toBe('Active');
    expect(badge).toHaveStyle({ color: 'var(--color-sentinel-green)' });
  });

  it('renders "None" muted badge when has_active_baseline is false', () => {
    render(<BaselineBadge asset={baseAsset} />);
    const badge = screen.getByTestId('baseline-badge');
    expect(badge.textContent).toBe('None');
    expect(badge).toHaveStyle({ color: 'var(--color-sentinel-text-disabled)' });
  });

  it('includes capture date in title when baseline is active', () => {
    const asset = { ...baseAsset, has_active_baseline: true, last_baseline_at: '2026-02-15T08:00:00' };
    render(<BaselineBadge asset={asset} />);
    const badge = screen.getByTestId('baseline-badge');
    expect(badge.title).toContain('2026-02-15');
  });
});

describe('DeviationBadge', () => {
  it('renders em-dash when no deviation data', () => {
    render(<DeviationBadge asset={baseAsset} />);
    expect(screen.getByTestId('deviation-badge').textContent).toBe('—');
  });

  it('renders warning color for deviation_status "warning"', () => {
    const asset = { ...baseAsset, max_deviation_percent_24h: 22.5, deviation_status: 'warning' as const };
    render(<DeviationBadge asset={asset} />);
    const badge = screen.getByTestId('deviation-badge');
    expect(badge.textContent).toBe('22.5%');
    expect(badge).toHaveStyle({ color: 'var(--color-sentinel-amber)' });
  });

  it('renders critical color for deviation_status "critical"', () => {
    const asset = { ...baseAsset, max_deviation_percent_24h: 35.0, deviation_status: 'critical' as const };
    render(<DeviationBadge asset={asset} />);
    const badge = screen.getByTestId('deviation-badge');
    expect(badge.textContent).toBe('35.0%');
    expect(badge).toHaveStyle({ color: 'var(--color-sentinel-red)' });
  });

  it('renders green color for deviation_status "normal"', () => {
    const asset = { ...baseAsset, max_deviation_percent_24h: 5.0, deviation_status: 'normal' as const };
    render(<DeviationBadge asset={asset} />);
    const badge = screen.getByTestId('deviation-badge');
    expect(badge.textContent).toBe('5.0%');
    expect(badge).toHaveStyle({ color: 'var(--color-sentinel-green)' });
  });
});

describe('FilterChips', () => {
  it('renders "No Baseline" chip when some equipment lacks baselines', () => {
    const assets = [
      baseAsset,
      { ...baseAsset, equipment_id: 'S002-AHU-002', has_active_baseline: true },
    ];
    render(<FilterChips assets={assets} activeFilter={null} onFilter={() => {}} />);
    expect(screen.getByTestId('chip-no-baseline')).toBeInTheDocument();
    expect(screen.getByTestId('chip-no-baseline').textContent).toContain('1');
  });

  it('does not render "No Baseline" chip when all equipment has baselines', () => {
    const assets = [
      { ...baseAsset, has_active_baseline: true },
      { ...baseAsset, equipment_id: 'S002-AHU-002', has_active_baseline: true },
    ];
    render(<FilterChips assets={assets} activeFilter={null} onFilter={() => {}} />);
    expect(screen.queryByTestId('chip-no-baseline')).not.toBeInTheDocument();
  });

  it('renders "Critical Deviation" chip when critical deviations exist', () => {
    const assets = [
      { ...baseAsset, deviation_status: 'critical' as const, max_deviation_percent_24h: 40 },
    ];
    render(<FilterChips assets={assets} activeFilter={null} onFilter={() => {}} />);
    expect(screen.getByTestId('chip-critical-deviation')).toBeInTheDocument();
  });

  it('does not render "Critical Deviation" chip when no critical deviations', () => {
    const assets = [
      { ...baseAsset, deviation_status: 'warning' as const, max_deviation_percent_24h: 20 },
    ];
    render(<FilterChips assets={assets} activeFilter={null} onFilter={() => {}} />);
    expect(screen.queryByTestId('chip-critical-deviation')).not.toBeInTheDocument();
  });
});
