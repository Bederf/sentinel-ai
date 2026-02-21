/**
 * Tests for Phase 108 monitoring components:
 * - IngestionModeBanner: renders 3 mode variants with correct styling
 * - MonitoringKPIPanel: renders 8 KPI cards with correct titles and values
 * - CommissioningGatePanel: renders null → muted message, renders gates with icons
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IngestionModeBanner } from '../system/IngestionModeBanner';
import { MonitoringKPIPanel } from '../system/MonitoringKPIPanel';
import { CommissioningGatePanel } from '../system/CommissioningGatePanel';
import type { IngestionKPIs, ControlKPIs, CommissioningSnapshot } from '@/lib/api/system';

// Mock lucide-react icons to render as simple spans
vi.mock('lucide-react', () => {
  const icon = (name: string) => {
    const Component = (props: any) => <span data-testid={`icon-${name}`} {...props} />;
    Component.displayName = name;
    return Component;
  };
  return {
    Clock: icon('Clock'),
    AlertTriangle: icon('AlertTriangle'),
    Target: icon('Target'),
    Unlink: icon('Unlink'),
    Ghost: icon('Ghost'),
    ShieldOff: icon('ShieldOff'),
    CheckCircle: icon('CheckCircle'),
    ShieldAlert: icon('ShieldAlert'),
    XCircle: icon('XCircle'),
    Shield: icon('Shield'),
    TrendingUp: icon('TrendingUp'),
    TrendingDown: icon('TrendingDown'),
    Minus: icon('Minus'),
  };
});

// Mock KPICard to verify props passed through
vi.mock('@/components/KPICard', () => ({
  KPICard: ({ title, value }: { title: string; value: string | number }) => (
    <div data-testid={`kpi-${title}`}>{value}</div>
  ),
}));

// ==================== IngestionModeBanner ====================

describe('IngestionModeBanner', () => {
  it('renders SIMULATION mode with correct label', () => {
    render(<IngestionModeBanner mode="simulation" isLive={false} />);
    expect(screen.getByText('SIMULATION')).toBeDefined();
    expect(screen.getByText('OFFLINE')).toBeDefined();
  });

  it('renders SHADOW_LIVE mode with correct label', () => {
    render(<IngestionModeBanner mode="shadow_live" isLive={true} />);
    expect(screen.getByText('SHADOW LIVE')).toBeDefined();
    expect(screen.getByText('LIVE')).toBeDefined();
  });

  it('renders LIVE_CONTROL mode with correct label', () => {
    render(<IngestionModeBanner mode="live_control" isLive={true} />);
    expect(screen.getByText('LIVE CONTROL')).toBeDefined();
    expect(screen.getByText('LIVE')).toBeDefined();
  });
});

// ==================== MonitoringKPIPanel ====================

describe('MonitoringKPIPanel', () => {
  const ingestion: IngestionKPIs = {
    freshness_hours: 0.5,
    error_rate: 2.3,
    unmatched_points: 7,
    total_points: 120,
    match_coverage: 94.2,
    provenance_summary: { live_protocol: 3, file_manual: 0 },
  };

  const control: ControlKPIs = {
    shadow_writes_24h: 12,
    blocked_writes_24h: 3,
    approved_writes_24h: 8,
    safety_violations_24h: 1,
  };

  it('renders all 8 KPI cards', () => {
    render(<MonitoringKPIPanel ingestion={ingestion} control={control} />);

    // Ingestion row
    expect(screen.getByTestId('kpi-Freshness')).toBeDefined();
    expect(screen.getByTestId('kpi-Error Rate')).toBeDefined();
    expect(screen.getByTestId('kpi-Match Coverage')).toBeDefined();
    expect(screen.getByTestId('kpi-Unmatched')).toBeDefined();

    // Control row
    expect(screen.getByTestId('kpi-Shadow Writes')).toBeDefined();
    expect(screen.getByTestId('kpi-Blocked')).toBeDefined();
    expect(screen.getByTestId('kpi-Approved')).toBeDefined();
    expect(screen.getByTestId('kpi-Safety Violations')).toBeDefined();
  });

  it('displays correct values', () => {
    render(<MonitoringKPIPanel ingestion={ingestion} control={control} />);

    expect(screen.getByTestId('kpi-Freshness').textContent).toBe('0.5h');
    expect(screen.getByTestId('kpi-Error Rate').textContent).toBe('2.3%');
    expect(screen.getByTestId('kpi-Match Coverage').textContent).toBe('94%');
    expect(screen.getByTestId('kpi-Unmatched').textContent).toBe('7');
    expect(screen.getByTestId('kpi-Shadow Writes').textContent).toBe('12');
    expect(screen.getByTestId('kpi-Blocked').textContent).toBe('3');
    expect(screen.getByTestId('kpi-Approved').textContent).toBe('8');
    expect(screen.getByTestId('kpi-Safety Violations').textContent).toBe('1');
  });

  it('renders section headers', () => {
    render(<MonitoringKPIPanel ingestion={ingestion} control={control} />);
    expect(screen.getByText('Ingestion Health')).toBeDefined();
    expect(screen.getByText('Control Activity (24h)')).toBeDefined();
  });
});

// ==================== CommissioningGatePanel ====================

describe('CommissioningGatePanel', () => {
  it('renders muted message when commissioning is null', () => {
    render(<CommissioningGatePanel commissioning={null} />);
    expect(screen.getByText(/not applicable in simulation mode/i)).toBeDefined();
  });

  it('renders GO badge when all gates passed', () => {
    const commissioning: CommissioningSnapshot = {
      gates_passed: 8,
      gates_total: 8,
      all_gates_passed: true,
      consecutive_pass_days: 3,
      can_promote: true,
      blocking_gates: [],
    };
    render(<CommissioningGatePanel commissioning={commissioning} />);
    expect(screen.getByText('GO')).toBeDefined();
    expect(screen.getByText('Ready to promote')).toBeDefined();
  });

  it('renders NO-GO badge with blocking gates', () => {
    const commissioning: CommissioningSnapshot = {
      gates_passed: 6,
      gates_total: 8,
      all_gates_passed: false,
      consecutive_pass_days: 1,
      can_promote: false,
      blocking_gates: ['match_coverage', 'error_rate'],
    };
    render(<CommissioningGatePanel commissioning={commissioning} />);
    expect(screen.getByText('NO-GO')).toBeDefined();
    expect(screen.getByText('Not ready')).toBeDefined();
    expect(screen.getByText(/6\/8 gates passed/)).toBeDefined();
  });
});
