import { useState, useEffect, useCallback } from 'react';
import { Leaf, CloudOff } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

import { Badge } from '../Badge';
import { PageLoading } from '../PageLoading';
import { sustainabilityApi } from '../../lib/sustainabilityApi';
import type {
  SustainabilitySummary,
  EmissionsHistory,
  EfficiencyMetrics,
  GreenStarAssessment,
} from '../../lib/sustainabilityApi';
import type { Site } from '../../lib/api';
import { api } from '../../lib/api';
import { sustainabilityApi as sustainabilityV2Api } from '../../lib/api/sustainability';
import type { ESGMetrics } from '../../lib/api/sustainability';

interface SustainabilityDashboardProps {
  siteId?: string;
  onAIRecommendation?: (recommendation: {
    id: string;
    type: string;
    priority: 'low' | 'medium' | 'high' | 'critical';
    title: string;
    description: string;
    source_module: string;
    related_modules?: string[];
    action?: { type: string; target: string; value: unknown };
    timestamp: string;
  }) => void;
  enabledModules?: string[];
}

export function SustainabilityDashboard({
  siteId: _externalSiteId,
  enabledModules: _enabledModules = ['compliance'],
}: SustainabilityDashboardProps) {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');
  const [summary, setSummary] = useState<SustainabilitySummary | null>(null);
  const [history, setHistory] = useState<EmissionsHistory | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyMetrics | null>(null);
  const [greenStar, setGreenStar] = useState<GreenStarAssessment | null>(null);
  const [esgMetrics, setEsgMetrics] = useState<ESGMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [sitesLoading, setSitesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSites()
      .then((fetchedSites) => {
        setSites(fetchedSites);
        if (fetchedSites.length > 0) {
          const defaultSite =
            fetchedSites.find((site) => site.id === "site-002")
            ?? fetchedSites.find((site) => /sandton city office tower/i.test(site.name))
            ?? fetchedSites[0];
          const initialSite = _externalSiteId || defaultSite.id;
          setSelectedSiteId(initialSite);
        }
      })
      .catch(() => {
        setSites([]);
        setSelectedSiteId(_externalSiteId || '');
      })
      .finally(() => {
        setSitesLoading(false);
      });
  }, [_externalSiteId]);

  const loadData = useCallback(async () => {
    if (!selectedSiteId) return;

    try {
      setLoading(true);
      setError(null);
      const s = await sustainabilityApi.fetchSummary(selectedSiteId);
      await new Promise((resolve) => setTimeout(resolve, 400));
      const h = await sustainabilityApi.fetchEmissions(selectedSiteId, 12);
      await new Promise((resolve) => setTimeout(resolve, 400));
      const e = await sustainabilityApi.fetchEfficiency(selectedSiteId);
      await new Promise((resolve) => setTimeout(resolve, 400));
      const g = await sustainabilityApi.fetchGreenStar(selectedSiteId);
      setSummary(s);
      setHistory(h);
      setEfficiency(e);
      setGreenStar(g);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sustainability data');
    } finally {
      setLoading(false);
    }
  }, [selectedSiteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  useEffect(() => {
    if (selectedSiteId) {
      sustainabilityV2Api.getESGMetrics(selectedSiteId)
        .then(setEsgMetrics)
        .catch(() => setEsgMetrics(null));
    }
  }, [selectedSiteId]);

  if (sitesLoading || !selectedSiteId) {
    return <PageLoading message="Loading sustainability data..." />;
  }

  if (loading && !summary) {
    return <PageLoading message="Loading sustainability data..." />;
  }

  if (error) {
    return (
      <div
        className="rounded-lg p-4 md:p-5"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid rgba(220, 38, 38, 0.35)',
          borderRadius: 8,
        }}
      >
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>Sustainability & ESG</h2>
        <p className="mt-2" style={{ color: 'var(--color-sentinel-red)' }}>{error}</p>
      </div>
    );
  }

  const trendColor = summary?.trend === 'improving' ? 'emerald'
    : summary?.trend === 'worsening' ? 'red' : 'gray';
  const trendLabel = summary?.trend === 'improving' ? 'Improving'
    : summary?.trend === 'worsening' ? 'Worsening' : 'Stable';

  const currentMonth = summary?.current_month;
  const dataSource = currentMonth?.data_source;

  const trendBadgeStyle = trendColor === 'emerald'
    ? { background: 'rgba(16, 185, 129, 0.15)', color: 'var(--color-sentinel-green)' }
    : trendColor === 'red'
    ? { background: 'rgba(220, 38, 38, 0.15)', color: 'var(--color-sentinel-red)' }
    : { background: 'rgba(142, 142, 142, 0.15)', color: 'var(--color-sentinel-text-secondary)' };

  const systemBreakdownData = [
    { name: 'HVAC', value: currentMonth?.hvac_kg_co2 || 0 },
    { name: 'Lighting', value: currentMonth?.lighting_kg_co2 || 0 },
    { name: 'Other Electrical', value: currentMonth?.other_kg_co2 || 0 },
    { name: 'Diesel (Generators)', value: currentMonth?.scope1_kg_co2 || 0 },
    { name: 'Water & Waste', value: currentMonth?.scope3_kg_co2 || 0 },
  ].filter(d => d.value > 0);

  const chartData = (history?.data || []).map(d => ({
    month: d.month.slice(5),
    'Scope 1 (Diesel)': Math.round(d.scope1_kg_co2 / 1000 * 100) / 100,
    'Scope 2 (Grid)': Math.round(d.scope2_kg_co2 / 1000 * 100) / 100,
    'Scope 3 (Other)': Math.round(d.scope3_kg_co2 / 1000 * 100) / 100,
  }));

  const safeEnergyIntensity = efficiency?.energy_intensity_kwh_per_sqm_yr != null && Number.isFinite(efficiency.energy_intensity_kwh_per_sqm_yr)
    ? Math.round(efficiency.energy_intensity_kwh_per_sqm_yr)
    : null;
  const safeCarbonIntensity = efficiency?.carbon_intensity_kg_per_sqm_yr != null && Number.isFinite(efficiency.carbon_intensity_kg_per_sqm_yr)
    ? Math.round(efficiency.carbon_intensity_kg_per_sqm_yr * 10) / 10
    : null;

  const energyBars = efficiency ? [
    {
      name: 'Your Site',
      value: safeEnergyIntensity ?? 0,
      label: safeEnergyIntensity != null ? `${safeEnergyIntensity} kWh/sqm` : 'Awaiting data',
    },
    { name: 'SA Typical', value: efficiency.benchmarks?.energy_typical ?? 170 },
    { name: 'SA Efficient', value: efficiency.benchmarks?.energy_efficient ?? 120 },
  ] : [];

  const carbonBars = efficiency ? [
    {
      name: 'Your Site',
      value: safeCarbonIntensity ?? 0,
      label: safeCarbonIntensity != null ? `${safeCarbonIntensity} kg/sqm` : 'Awaiting data',
    },
    { name: 'SA Typical', value: efficiency.benchmarks?.carbon_typical ?? 85 },
    { name: 'SA Efficient', value: efficiency.benchmarks?.carbon_efficient ?? 55 },
  ] : [];

  const maxEnergyValue = Math.max(...energyBars.map(b => b.value), 1);
  const maxCarbonValue = Math.max(...carbonBars.map(b => b.value), 1);

  const donutColors = ['var(--color-sentinel-blue)', 'var(--color-sentinel-amber)', 'var(--color-sentinel-text-secondary)', 'var(--color-sentinel-red)', '#a78bfa'];
  const stackedColors = ['var(--color-sentinel-green)', 'var(--color-sentinel-amber)', 'var(--color-sentinel-text-secondary)'];

  return (
    <div className="space-y-6 p-4 md:p-6" style={{ background: "var(--color-grafana-bg-canvas)" }}>
      <div
        className="panel rounded-lg p-4 md:p-5 flex items-center justify-between flex-wrap gap-3"
        style={{ border: "1px solid var(--color-grafana-border)", background: 'var(--color-sentinel-bg-panel)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: 'rgba(16, 185, 129, 0.15)' }}
          >
            <Leaf className="h-5 w-5" style={{ color: 'var(--color-sentinel-green)' }} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2
                className="text-lg font-semibold"
                style={{ color: 'var(--color-grafana-text-primary)' }}
              >
                Sustainability & ESG
              </h2>
              {dataSource && (
                <Badge
                  style={{
                    background: dataSource === 'measured' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    color: dataSource === 'measured' ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
                    border: dataSource !== 'measured' ? '1px solid rgba(245, 158, 11, 0.3)' : undefined,
                    textTransform: 'uppercase',
                    letterSpacing: '0.03em',
                  }}
                >
                  {dataSource === 'measured' ? 'Live Data' : 'Estimated'}
                </Badge>
              )}
            </div>
            <p
              className="text-xs"
              style={{ color: 'var(--color-grafana-text-secondary)' }}
            >
              Carbon emissions, efficiency metrics, and Green Star SA tracker
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {!sitesLoading && sites.length > 0 && (
            <select
              value={selectedSiteId}
              onChange={(event) => setSelectedSiteId(event.target.value)}
              className="w-56 rounded-md appearance-none cursor-pointer px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-0"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
                color: "var(--color-grafana-text-primary)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
                outline: "none",
              }}
              aria-label="Select site"
            >
              {sites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.name}
                </option>
              ))}
            </select>
          )}
          <button
            className="px-2.5 py-1.5 rounded text-xs font-medium transition-colors"
            style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)', cursor: 'pointer' }}
            onClick={() => window.open(`/api/sustainability/${selectedSiteId}/report/export?format=csv&months=12`)}
          >
            Export CSV
          </button>
          <button
            className="px-2.5 py-1.5 rounded text-xs font-medium transition-colors"
            style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)', cursor: 'pointer' }}
            onClick={() => window.open(`/api/sustainability/${selectedSiteId}/report/export?format=html&months=12`)}
          >
            Export Report
          </button>
        </div>
      </div>

      <div className={`grid grid-cols-2 ${esgMetrics ? 'lg:grid-cols-5' : 'lg:grid-cols-4'} gap-4`}>
        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <p style={{ color: 'var(--color-grafana-text-secondary)' }}>
            Total CO2 YTD
          </p>
          <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-grafana-text-primary)' }}>
            {summary?.ytd.total_co2_tonnes.toFixed(1) ?? '—'} t
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Badge style={trendBadgeStyle}>
              {trendLabel}
            </Badge>
            <span className="text-xs" style={{ color: 'var(--color-grafana-text-secondary)' }}>
              {`Target: -${summary?.target_reduction_pct ?? 10}% YoY`}
            </span>
          </div>
        </div>

        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <p style={{ color: 'var(--color-grafana-text-secondary)' }}>Carbon Intensity</p>
          <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-grafana-text-primary)' }}>
            {summary?.carbon_intensity_kg_per_sqm
              ? summary.carbon_intensity_kg_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kg/sqm</span>
          </div>
          <p className="text-xs mt-2" style={{ color: 'var(--color-grafana-text-secondary)' }}>Current month</p>
          {currentMonth?.solar_offset_kg_co2 != null && currentMonth.solar_offset_kg_co2 > 0 && (
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-green)' }}>
              Solar offset: -{(currentMonth.solar_offset_kg_co2 / 1000).toFixed(1)}t CO2
            </p>
          )}
        </div>

        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <p style={{ color: 'var(--color-grafana-text-secondary)' }}>Energy Intensity</p>
          <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-grafana-text-primary)' }}>
            {summary?.energy_intensity_kwh_per_sqm
              ? summary.energy_intensity_kwh_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kWh/sqm</span>
          </div>
          <p className="text-xs mt-2" style={{ color: 'var(--color-grafana-text-secondary)' }}>Current month</p>
        </div>

        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <p style={{ color: 'var(--color-grafana-text-secondary)' }}>Green Star Progress</p>
          <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-grafana-text-primary)' }}>
            {summary?.green_star.total_achieved ?? 0}
            <span className="text-sm font-normal">
              /{summary?.green_star.total_max ?? 118} pts
            </span>
          </div>
          <Badge style={{ background: 'rgba(167, 139, 250, 0.15)', color: '#a78bfa' }} className="mt-2">
            {summary?.green_star.estimated_rating ?? '—'}
          </Badge>
        </div>

        {esgMetrics && (
          <div
            className="panel rounded-lg p-4"
            style={{
              background: 'var(--color-sentinel-bg-panel)',
              borderTop: `3px solid ${
                esgMetrics.overall_esg_score >= 80 ? 'var(--color-sentinel-green)'
                : esgMetrics.overall_esg_score >= 60 ? 'var(--color-sentinel-amber)'
                : 'var(--color-sentinel-red)'
              }`,
              borderLeft: '1px solid var(--color-grafana-border)',
              borderRight: '1px solid var(--color-grafana-border)',
              borderBottom: '1px solid var(--color-grafana-border)',
            }}
          >
            <p style={{ color: 'var(--color-grafana-text-secondary)' }}>ESG Score</p>
            <div className="text-3xl font-semibold tabular-nums" style={{ color: 'var(--color-grafana-text-primary)' }}>
              {esgMetrics.overall_esg_score ?? '—'}/100
            </div>
            <p className="text-xs mt-1" style={{ color: 'var(--color-grafana-text-secondary)' }}>
              Carbon: {esgMetrics.carbon_intensity_score}% |
              Energy: {esgMetrics.energy_efficiency_score}% |
              Waste: {esgMetrics.waste_diversion_score}%
            </p>
          </div>
        )}
      </div>

      <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>Monthly Emissions by Scope (tonnes CO2)</h2>
        <p className="mb-4" style={{ color: 'var(--color-grafana-text-secondary)' }}>
          Scope 1: Diesel generators | Scope 2: Grid electricity | Scope 3: Water, waste, commuting
        </p>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={288}>
            <BarChart data={chartData}>
              <CartesianGrid stroke="var(--color-sentinel-border)" strokeDasharray="2 4" />
              <XAxis dataKey="month" stroke="var(--color-sentinel-text-secondary)" tick={{fontSize: 11}} />
              <YAxis stroke="var(--color-sentinel-text-secondary)" tick={{fontSize: 11}} />
              <Tooltip
                contentStyle={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)', borderRadius: 6 }}
              />
              <Bar dataKey="Scope 1 (Diesel)" fill={stackedColors[0]} stackId="a" />
              <Bar dataKey="Scope 2 (Grid)" fill={stackedColors[1]} stackId="a" />
              <Bar dataKey="Scope 3 (Other)" fill={stackedColors[2]} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center flex-col gap-2" style={{ color: 'var(--color-grafana-text-disabled)' }}>
            <CloudOff className="h-8 w-8 opacity-50" />
            <p style={{ color: 'var(--color-grafana-text-disabled)' }}>No emissions data available</p>
          </div>
        )}
      </div>

      {systemBreakdownData.length > 0 && (
        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>Carbon by System</h2>
          <p className="text-xs" style={{ color: 'var(--color-grafana-text-disabled)' }}>
            Source: {dataSource === 'measured' ? 'Metered Data' : 'Estimated'}
          </p>
          <div className="mt-4" style={{ height: 192 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={systemBreakdownData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3}>
                  {systemBreakdownData.map((_entry, index) => (
                    <Cell key={`cell-${index}`} fill={donutColors[index % donutColors.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)', borderRadius: 6 }}
                  formatter={(value: number) => [`${(value / 1000).toFixed(1)}t`]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>Energy Intensity vs SA Benchmarks</h2>
          <p className="mb-3" style={{ color: 'var(--color-grafana-text-secondary)' }}>kWh per sqm per year</p>
          <div className="mt-2 space-y-2">
            {energyBars.map(bar => (
              <div key={bar.name} className="flex items-center gap-3">
                <span className="text-sm w-28 flex-shrink-0" style={{ color: 'var(--color-grafana-text-secondary)' }}>{bar.name}</span>
                <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
                  <div className="h-full rounded-full" style={{ width: `${(bar.value / maxEnergyValue) * 100}%`, background: 'var(--color-sentinel-amber)' }} />
                </div>
                <span className="text-sm font-medium tabular-nums w-28 text-right flex-shrink-0" style={{ color: 'var(--color-grafana-text-primary)' }}>{bar.label}</span>
              </div>
            ))}
          </div>
          {efficiency?.vs_typical && (
            <p className="text-xs mt-3" style={{ color: 'var(--color-grafana-text-secondary)' }}>
              {efficiency.vs_typical.energy_pct > 0
                ? `${efficiency.vs_typical.energy_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.energy_pct)}% below typical`}
            </p>
          )}
        </div>

        <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>Carbon Intensity vs SA Benchmarks</h2>
          <p className="mb-3" style={{ color: 'var(--color-grafana-text-secondary)' }}>kg CO2 per sqm per year</p>
          <div className="mt-2 space-y-2">
            {carbonBars.map(bar => (
              <div key={bar.name} className="flex items-center gap-3">
                <span className="text-sm w-28 flex-shrink-0" style={{ color: 'var(--color-grafana-text-secondary)' }}>{bar.name}</span>
                <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
                  <div className="h-full rounded-full" style={{ width: `${(bar.value / maxCarbonValue) * 100}%`, background: 'var(--color-sentinel-green)' }} />
                </div>
                <span className="text-sm font-medium tabular-nums w-28 text-right flex-shrink-0" style={{ color: 'var(--color-grafana-text-primary)' }}>{bar.label}</span>
              </div>
            ))}
          </div>
          {efficiency?.vs_typical && (
            <p className="text-xs mt-3" style={{ color: 'var(--color-grafana-text-secondary)' }}>
              {efficiency.vs_typical.carbon_pct > 0
                ? `${efficiency.vs_typical.carbon_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.carbon_pct)}% below typical`}
            </p>
          )}
        </div>
      </div>

      <div className="panel rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="text-lg font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>Green Star SA Self-Assessment</h2>
            <p style={{ color: 'var(--color-grafana-text-secondary)' }}>{greenStar?.tool_version ?? 'Green Star SA Office v1.1'}</p>
          </div>
          <div className="text-right">
            <Badge style={{ background: 'rgba(167, 139, 250, 0.15)', color: '#a78bfa', padding: '4px 12px', fontSize: '0.875rem' }}>
              {greenStar?.estimated_star_rating ?? '—'}
            </Badge>
            <p className="text-xs mt-1" style={{ color: 'var(--color-grafana-text-secondary)' }}>
              Target: {greenStar?.target_rating ?? '5-Star'}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(greenStar?.categories || []).map(cat => {
            const pct = cat.max_points > 0
              ? Math.round((cat.achieved_points / cat.max_points) * 100)
              : 0;
            const barColor = pct >= 75 ? 'var(--color-sentinel-green)' : pct >= 50 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-red)';
            const targetPct = cat.max_points > 0 && cat.target_points > 0
              ? Math.round((cat.target_points / cat.max_points) * 100)
              : 0;

            return (
              <div key={cat.category_id} className="panel p-3 rounded-lg" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-grafana-border)' }}>
                <div className="flex justify-between items-center mb-2">
                  <p className="font-semibold text-sm" style={{ color: 'var(--color-grafana-text-primary)' }}>{cat.name}</p>
                  <p className="text-xs font-mono" style={{ color: 'var(--color-grafana-text-disabled)' }}>{cat.category_id}</p>
                </div>

                <div className="text-center my-2">
                  <span style={{ fontSize: '1.75rem', fontWeight: 700, color: barColor, lineHeight: 1 }}>
                    {cat.achieved_points}
                  </span>
                  <span style={{ fontSize: '1rem', fontWeight: 400, color: 'var(--color-grafana-text-disabled)' }}>
                    {' '}/ {cat.max_points}
                  </span>
                </div>

                <div className="relative mt-1" style={{ height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.08)' }}>
                  <div
                    style={{
                      height: '100%',
                      width: '100%',
                      borderRadius: 4,
                      background: barColor,
                      transform: `scaleX(${Math.max(pct, 0.5) / 100})`,
                      transformOrigin: 'left',
                      willChange: 'transform',
                      transition: 'transform 0.6s ease',
                    }}
                  />
                  {targetPct > 0 && (
                    <div
                      style={{
                        position: 'absolute',
                        left: `${targetPct}%`,
                        top: -2,
                        bottom: -2,
                        width: 2,
                        background: 'rgba(255,255,255,0.5)',
                        borderRadius: 1,
                      }}
                      title={`Target: ${cat.target_points} pts`}
                    />
                  )}
                </div>

                <div className="flex justify-between mt-1.5">
                  <p className="text-xs" style={{ color: 'var(--color-grafana-text-secondary)' }}>
                    {cat.target_points > 0 ? `Target: ${cat.target_points} pts` : '\u00A0'}
                  </p>
                  <p className="text-xs font-mono" style={{ color: 'var(--color-grafana-text-disabled)' }}>
                    {pct}%
                  </p>
                </div>

                {cat.notes && (
                  <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--color-grafana-text-disabled)' }}>
                    {cat.notes}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {greenStar && (
          <div className="flex justify-end items-baseline mt-4 gap-2">
            <p className="text-sm" style={{ color: 'var(--color-grafana-text-secondary)' }}>Total:</p>
            <span style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-grafana-text-primary)' }}>
              {greenStar.total_achieved}
            </span>
            <span style={{ fontSize: '0.875rem', color: 'var(--color-grafana-text-disabled)' }}>
              / {greenStar.total_max} pts
            </span>
            {greenStar.total_target > 0 && (
              <p className="text-sm" style={{ color: 'var(--color-grafana-text-secondary)' }}>
                (target: {greenStar.total_target})
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default SustainabilityDashboard;
