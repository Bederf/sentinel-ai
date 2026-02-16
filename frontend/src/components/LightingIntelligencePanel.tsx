// @ts-nocheck
import { useState, useEffect } from 'react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Lightbulb, TrendingUp, Brain, Sun, Users, Zap } from 'lucide-react';

interface DaliSimulation {
  summary: {
    baseline_annual_cost: number;
    dali_annual_cost: number;
    sentinel_annual_cost: number;
    total_savings_zar: number;
    dali_savings_zar: number;
    sentinel_additional_zar: number;
    savings_pct: number;
    occupancy_hours_saved: number;
    daylight_hours_utilized: number;
    ml_effectiveness_pct: number;
  };
  daily_data: Array<{
    day: number;
    date: string;
    baseline_cumulative: number;
    dali_cumulative: number;
    sentinel_cumulative: number;
    savings: number;
    learning_factor: number;
  }>;
  monthly_data: Array<{
    month: string;
    baseline_cost: number;
    dali_cost: number;
    sentinel_cost: number;
    baseline_kwh: number;
    dali_kwh: number;
    sentinel_kwh: number;
  }>;
}

export function LightingIntelligencePanel({ siteId }: { siteId: string }) {
  const [data, setData] = useState<DaliSimulation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSimulation();
  }, [siteId]);

  const fetchSimulation = async () => {
    try {
      const response = await fetch(`/api/dali/simulation?site_id=${siteId}`);
      if (!response.ok) {
        console.error('Failed to fetch DALI simulation:', response.status, response.statusText);
        setLoading(false);
        return;
      }
      const json = await response.json();
      if (!json || !json.summary) {
        console.warn('DALI simulation response missing summary:', json);
      }
      setData(json);
    } catch (error) {
      console.error('Failed to load DALI simulation:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center rounded-lg" style={{ background: 'var(--color-sentinel-bg-panel)' }}>
        <div className="animate-spin h-8 w-8 border-4 border-amber-500 border-t-transparent rounded-full mx-auto mb-4" />
        <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Running 365-day DALI simulation...
        </p>
      </div>
    );
  }

  if (!data || !data.summary) return null;

  const { summary, daily_data, monthly_data } = data;

  // Validate required data exists
  if (!summary.baseline_annual_cost || !summary.sentinel_annual_cost) {
    return (
      <div className="p-8 text-center rounded-lg" style={{ background: 'var(--color-sentinel-bg-panel)' }}>
        <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          DALI simulation data is incomplete or unavailable
        </p>
      </div>
    );
  }

  // Format helpers
  const fmtR = (v: number) => `R ${Math.round(v).toLocaleString()}`;
  const fmtRK = (v: number) => `R ${(v / 1000).toFixed(0)}k`;
  const fmtPct = (v: number) => `${v.toFixed(1)}%`;

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
      <div
        style={{
          background: 'rgba(15, 20, 30, 0.95)',
          border: '1px solid var(--color-sentinel-border)',
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 12,
        }}
      >
        <div
          style={{
            fontWeight: 600,
            marginBottom: 6,
            color: 'var(--color-sentinel-text-primary)',
          }}
        >
          {label}
        </div>
        {payload.map((p: any, i: number) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 6,
              marginBottom: 2,
              color: 'var(--color-sentinel-text-secondary)',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: p.color,
                marginTop: 4,
              }}
            />
            <span>{p.name}:</span>
            <span style={{ fontWeight: 600, color: p.color }}>
              {typeof p.value === 'number' ? fmtR(p.value) : p.value}
            </span>
          </div>
        ))}
      </div>
    );
  };

  // Calculate energy reduction percentage (with safety check)
  const energyReductionPct =
    summary.baseline_annual_cost > 0
      ? ((summary.baseline_annual_cost - summary.sentinel_annual_cost) /
          summary.baseline_annual_cost) *
        100
      : 0;

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
        style={{
          borderBottom: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: 'rgba(250, 204, 21, 0.15)' }}
          >
            <Lightbulb className="h-5 w-5" style={{ color: '#FACC15' }} />
          </div>
          <div>
            <h3
              className="font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Wardew Smart Lighting Intelligence
            </h3>
            <span
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              365-Day Comparative Simulation · Site-002 Sandton Office Complex
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded"
          style={{
            background: 'rgba(34, 197, 94, 0.15)',
            color: '#22C55E',
          }}
        >
          {fmtPct(summary.savings_pct)} Total Savings
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* Hero Metrics */}
        <div className="grid grid-cols-3 gap-3">
          <MetricCard
            icon={<TrendingUp className="h-5 w-5" />}
            label="Annual Savings"
            value={fmtRK(summary.total_savings_zar)}
            subtitle="Sentinel vs Baseline"
            color="#22C55E"
          />
          <MetricCard
            icon={<Zap className="h-5 w-5" />}
            label="Energy Reduced"
            value={`${energyReductionPct.toFixed(0)}%`}
            subtitle={`${fmtRK(
              summary.baseline_annual_cost - summary.sentinel_annual_cost
            )} grid energy saved`}
            color="#FACC15"
          />
          <MetricCard
            icon={<Brain className="h-5 w-5" />}
            label="AI Accuracy"
            value={`${summary.ml_effectiveness_pct}%`}
            subtitle="ML learning effectiveness"
            color="#00D2FF"
          />
        </div>

        {/* Cumulative Savings Chart */}
        <div>
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Cumulative Cost Over 365 Days
          </h4>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={daily_data}>
              <defs>
                <linearGradient id="gradBaseline" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6B7280" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6B7280" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradDali" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#F59E0B" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradSentinel" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22C55E" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#22C55E" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--color-sentinel-border)"
              />
              <XAxis
                dataKey="day"
                tick={{
                  fill: 'var(--color-sentinel-text-secondary)',
                  fontSize: 10,
                }}
                axisLine={{ stroke: 'var(--color-sentinel-border)' }}
              />
              <YAxis
                tick={{
                  fill: 'var(--color-sentinel-text-secondary)',
                  fontSize: 10,
                }}
                axisLine={{ stroke: 'var(--color-sentinel-border)' }}
                tickFormatter={(v) => fmtRK(v)}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="baseline_cumulative"
                stroke="#6B7280"
                fill="url(#gradBaseline)"
                strokeWidth={2}
                name="Baseline (No DALI)"
                dot={false}
              />
              <Area
                type="monotone"
                dataKey="dali_cumulative"
                stroke="#F59E0B"
                fill="url(#gradDali)"
                strokeWidth={2}
                name="With Smart Lighting (Tridonic)"
                dot={false}
              />
              <Area
                type="monotone"
                dataKey="sentinel_cumulative"
                stroke="#22C55E"
                fill="url(#gradSentinel)"
                strokeWidth={2}
                name="With SENTINEL AI"
                dot={false}
              />
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                contentStyle={{
                  background: 'transparent',
                  border: 'none',
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Savings Breakdown */}
        <div className="grid grid-cols-2 gap-3">
          <BreakdownCard
            icon={<Users className="h-4 w-4" />}
            title="Occupancy Detection"
            value={fmtR(summary.occupancy_hours_saved * 2.5)}
            subtitle={`${summary.occupancy_hours_saved.toLocaleString()} hours lights off when vacant`}
            color="#3B82F6"
          />
          <BreakdownCard
            icon={<Sun className="h-4 w-4" />}
            title="Daylight Harvesting"
            value={fmtR(summary.daylight_hours_utilized * 2.2)}
            subtitle={`${summary.daylight_hours_utilized.toLocaleString()} hours dimmed via natural light`}
            color="#F59E0B"
          />
        </div>

        {/* Monthly Savings Bar Chart */}
        <div>
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Monthly Cost Comparison (R thousands)
          </h4>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={monthly_data.map((m) => ({
                ...m,
                baseline_k: m.baseline_cost / 1000,
                dali_k: m.dali_cost / 1000,
                sentinel_k: m.sentinel_cost / 1000,
              }))}
              barGap={2}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--color-sentinel-border)"
              />
              <XAxis
                dataKey="month"
                tick={{
                  fill: 'var(--color-sentinel-text-secondary)',
                  fontSize: 10,
                }}
                axisLine={{ stroke: 'var(--color-sentinel-border)' }}
              />
              <YAxis
                tick={{
                  fill: 'var(--color-sentinel-text-secondary)',
                  fontSize: 10,
                }}
                axisLine={{ stroke: 'var(--color-sentinel-border)' }}
                tickFormatter={(v) => `${v.toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar
                dataKey="baseline_k"
                fill="#6B7280"
                name="Baseline (Rk)"
                radius={[4, 4, 0, 0]}
                opacity={0.6}
              />
              <Bar
                dataKey="dali_k"
                fill="#F59E0B"
                name="Smart Lighting (Rk)"
                radius={[4, 4, 0, 0]}
                opacity={0.8}
              />
              <Bar
                dataKey="sentinel_k"
                fill="#22C55E"
                name="Sentinel (Rk)"
                radius={[4, 4, 0, 0]}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </BarChart>
          </ResponsiveContainer>
          <p
            className="text-xs mt-2 text-center"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Summer months show higher savings due to longer daylight hours and
            thunderstorm cloud patterns
          </p>
        </div>

        {/* Value Proposition Callout */}
        <div
          className="p-3 rounded-lg"
          style={{
            background: 'rgba(34, 197, 94, 0.1)',
            border: '1px solid rgba(34, 197, 94, 0.3)',
          }}
        >
          <div className="flex items-start gap-3">
            <Brain
              className="h-5 w-5 mt-0.5"
              style={{ color: '#22C55E', flexShrink: 0 }}
            />
            <div>
              <p
                className="text-sm font-medium mb-1"
                style={{ color: '#22C55E' }}
              >
                Wardew Smart Lighting + SENTINEL AI Intelligence
              </p>
              <p
                className="text-xs leading-relaxed"
                style={{ color: 'rgba(34, 197, 94, 0.8)' }}
              >
                AI models learn building occupancy patterns, daylight
                availability, and weather forecasts over 12 months. Effectiveness
                improves from 60% (month 1) to 95% (month 12), delivering{' '}
                {fmtR(summary.total_savings_zar)} annual savings through occupancy
                detection, daylight harvesting, and predictive optimization.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper Components
function MetricCard({
  icon,
  label,
  value,
  subtitle,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtitle: string;
  color: string;
}) {
  return (
    <div
      className="p-3 rounded"
      style={{
        background: 'var(--color-sentinel-bg-secondary)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div style={{ color }}>{icon}</div>
        <span
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          {label}
        </span>
      </div>
      <div className="text-xl font-bold mb-1" style={{ color }}>
        {value}
      </div>
      <div
        className="text-xs"
        style={{ color: 'var(--color-sentinel-text-secondary)' }}
      >
        {subtitle}
      </div>
    </div>
  );
}

function BreakdownCard({
  icon,
  title,
  value,
  subtitle,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  subtitle: string;
  color: string;
}) {
  const rgbColor = color === '#3B82F6' ? '59, 130, 246' : '245, 158, 11';

  return (
    <div
      className="p-3 rounded"
      style={{
        background: `rgba(${rgbColor}, 0.08)`,
        border: `1px solid rgba(${rgbColor}, 0.2)`,
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <div style={{ color }}>{icon}</div>
        <span
          className="text-sm font-medium"
          style={{ color: 'var(--color-sentinel-text-primary)' }}
        >
          {title}
        </span>
      </div>
      <div className="text-lg font-bold mb-1" style={{ color }}>
        {value}
      </div>
      <div
        className="text-xs"
        style={{ color: 'var(--color-sentinel-text-secondary)' }}
      >
        {subtitle}
      </div>
    </div>
  );
}
