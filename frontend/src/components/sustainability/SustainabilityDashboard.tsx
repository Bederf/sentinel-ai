/**
 * Sustainability & ESG Dashboard - Bolt-on Module
 *
 * Displays carbon emissions, efficiency metrics, and Green Star SA tracker.
 * Derives all data from existing Energy module consumption data.
 */

import { useState, useEffect, useCallback } from 'react';
import { Leaf, CloudOff } from 'lucide-react';

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

  // Fetch sites on mount
  useEffect(() => {
    api.getSites()
      .then((fetchedSites) => {
        setSites(fetchedSites);
        if (fetchedSites.length > 0) {
          // Default to Sandton City Office Tower (site-002), or use provided siteId.
          const defaultSite =
            fetchedSites.find((site) => site.id === "site-002")
            ?? fetchedSites.find((site) => /sandton city office tower/i.test(site.name))
            ?? fetchedSites[0];
          const initialSite = _externalSiteId || defaultSite.id;
          setSelectedSiteId(initialSite);
        }
      })
      .catch(() => {
        // Fallback: empty state when API is unavailable
        // Fallback: empty state when API is unavailable
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
      // Stagger requests to avoid rate limiting
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

  // Fetch ESG metrics from v2 API (graceful fallback — may not be available)
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
      <Card className="glass-panel" style={{ border: "1px solid rgba(220, 38, 38, 0.35)" }}>
        <Title>Sustainability & ESG</Title>
        <Text className="mt-2" style={{ color: 'var(--color-sentinel-red)' }}>{error}</Text>
      </Card>
    );
  }

  const trendColor = summary?.trend === 'improving' ? 'emerald'
    : summary?.trend === 'worsening' ? 'red' : 'gray';
  const trendLabel = summary?.trend === 'improving' ? 'Improving'
    : summary?.trend === 'worsening' ? 'Worsening' : 'Stable';

  // Current month snapshot for per-system breakdown and data source
  const currentMonth = summary?.current_month;
  const dataSource = currentMonth?.data_source;

  // Per-system carbon breakdown data for DonutChart
  const systemBreakdownData = [
    { name: 'HVAC', value: currentMonth?.hvac_kg_co2 || 0 },
    { name: 'Lighting', value: currentMonth?.lighting_kg_co2 || 0 },
    { name: 'Other Electrical', value: currentMonth?.other_kg_co2 || 0 },
    { name: 'Diesel (Generators)', value: currentMonth?.scope1_kg_co2 || 0 },
    { name: 'Water & Waste', value: currentMonth?.scope3_kg_co2 || 0 },
  ].filter(d => d.value > 0);

  // Chart data: monthly emissions stacked by scope
  const chartData = (history?.data || []).map(d => ({
    month: d.month.slice(5), // MM only for compact labels
    'Scope 1 (Diesel)': Math.round(d.scope1_kg_co2 / 1000 * 100) / 100,
    'Scope 2 (Grid)': Math.round(d.scope2_kg_co2 / 1000 * 100) / 100,
    'Scope 3 (Other)': Math.round(d.scope3_kg_co2 / 1000 * 100) / 100,
  }));

  // Efficiency benchmark bars
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

  return (
    <div className="space-y-6 p-4 md:p-6" style={{ background: "var(--color-grafana-bg-canvas)" }}>
      {/* Header with Building Selector */}
      <div
        className="panel rounded-lg p-4 md:p-5 flex items-center justify-between flex-wrap gap-3"
        style={{ border: "1px solid var(--color-grafana-border)" }}
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
                  color={dataSource === 'measured' ? 'green' : 'amber'}
                  size="xs"
                  style={{
                    textTransform: 'uppercase',
                    letterSpacing: '0.03em',
                    ...(dataSource !== 'measured' ? { background: 'rgba(245, 158, 11, 0.15)', color: 'var(--color-sentinel-amber)', border: '1px solid rgba(245, 158, 11, 0.3)' } : undefined)
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

        {/* Building Selector + Export Buttons */}
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
          <Button
            size="xs"
            variant="secondary"
            onClick={() => window.open(`/api/sustainability/${selectedSiteId}/report/export?format=csv&months=12`)}
          >
            Export CSV
          </Button>
          <Button
            size="xs"
            variant="secondary"
            onClick={() => window.open(`/api/sustainability/${selectedSiteId}/report/export?format=html&months=12`)}
          >
            Export Report
          </Button>
        </div>
      </div>

      {/* KPI Row */}
      <Grid className={`grid grid-cols-2 ${esgMetrics ? 'lg:grid-cols-5' : 'lg:grid-cols-4'} gap-4`}>
        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Text style={{ color: "var(--color-grafana-text-secondary)" }}>
            Total CO2 YTD
          </Text>
          <Metric>{summary?.ytd.total_co2_tonnes.toFixed(1) ?? '—'} t</Metric>
          <Flex className="mt-2">
            <Badge color={trendColor} size="xs">
              {trendLabel}
            </Badge>
            <Text className="text-xs" style={{ color: "var(--color-grafana-text-secondary)" }}>
              {`Target: -${summary?.target_reduction_pct ?? 10}% YoY`}
            </Text>
          </Flex>
        </Card>

        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Text style={{ color: "var(--color-grafana-text-secondary)" }}>Carbon Intensity</Text>
          <Metric>
            {summary?.carbon_intensity_kg_per_sqm
              ? summary.carbon_intensity_kg_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kg/sqm</span>
          </Metric>
          <Text className="text-xs mt-2" style={{ color: "var(--color-grafana-text-secondary)" }}>Current month</Text>
          {currentMonth?.solar_offset_kg_co2 != null && currentMonth.solar_offset_kg_co2 > 0 && (
            <Text className="text-xs mt-1" style={{ color: 'var(--color-sentinel-green)' }}>
              Solar offset: -{(currentMonth.solar_offset_kg_co2 / 1000).toFixed(1)}t CO2
            </Text>
          )}
        </Card>

        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Text style={{ color: "var(--color-grafana-text-secondary)" }}>Energy Intensity</Text>
          <Metric>
            {summary?.energy_intensity_kwh_per_sqm
              ? summary.energy_intensity_kwh_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kWh/sqm</span>
          </Metric>
          <Text className="text-xs mt-2" style={{ color: "var(--color-grafana-text-secondary)" }}>Current month</Text>
        </Card>

        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Text style={{ color: "var(--color-grafana-text-secondary)" }}>Green Star Progress</Text>
          <Metric>
            {summary?.green_star.total_achieved ?? 0}
            <span className="text-sm font-normal">
              /{summary?.green_star.total_max ?? 118} pts
            </span>
          </Metric>
          <Badge color="violet" size="xs" className="mt-2">
            {summary?.green_star.estimated_rating ?? '—'}
          </Badge>
        </Card>

        {/* ESG Score from v2 API — hidden if unavailable */}
        {esgMetrics && (
          <Card
            className="panel"
            decoration="top"
            decorationColor={
              esgMetrics.overall_esg_score >= 80 ? 'green' :
              esgMetrics.overall_esg_score >= 60 ? 'amber' : 'red'
            }
            style={{ border: "1px solid var(--color-grafana-border)" }}
          >
            <Text style={{ color: "var(--color-grafana-text-secondary)" }}>ESG Score</Text>
            <Metric>{esgMetrics.overall_esg_score ?? '—'}/100</Metric>
            <Text className="text-xs mt-1" style={{ color: "var(--color-grafana-text-secondary)" }}>
              Carbon: {esgMetrics.carbon_intensity_score}% |
              Energy: {esgMetrics.energy_efficiency_score}% |
              Waste: {esgMetrics.waste_diversion_score}%
            </Text>
          </Card>
        )}
      </Grid>

      {/* Emissions Chart */}
      <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
        <Title>Monthly Emissions by Scope (tonnes CO2)</Title>
        <Text className="mb-4" style={{ color: "var(--color-grafana-text-secondary)" }}>
          Scope 1: Diesel generators | Scope 2: Grid electricity | Scope 3: Water, waste, commuting
        </Text>
        {chartData.length > 0 ? (
          <BarChart
            data={chartData}
            index="month"
            categories={['Scope 1 (Diesel)', 'Scope 2 (Grid)', 'Scope 3 (Other)']}
            colors={['green', 'amber', 'gray']}
            stack
            yAxisWidth={56}
            className="h-72"
          />
        ) : (
          <div className="flex items-center justify-center flex-col gap-2" style={{ color: 'var(--color-grafana-text-disabled)' }}>
            <CloudOff className="h-8 w-8 opacity-50" />
            <Text style={{ color: 'var(--color-grafana-text-disabled)' }}>No emissions data available</Text>
          </div>
        )}
      </Card>

      {/* Per-System Carbon Breakdown */}
      {systemBreakdownData.length > 0 && (
        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Title>Carbon by System</Title>
          <Text className="text-xs" style={{ color: "var(--color-grafana-text-disabled)" }}>
            Source: {dataSource === 'measured' ? 'Metered Data' : 'Estimated'}
          </Text>
          <DonutChart
            className="mt-4 h-48"
            data={systemBreakdownData}
            category="value"
            index="name"
            colors={['blue', 'amber', 'gray', 'red', 'violet']}
            valueFormatter={(v: number) => `${(v / 1000).toFixed(1)}t`}
          />
        </Card>
      )}

      {/* Efficiency vs Benchmarks */}
      <Grid className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Title>Energy Intensity vs SA Benchmarks</Title>
          <Text className="mb-3" style={{ color: "var(--color-grafana-text-secondary)" }}>kWh per sqm per year</Text>
          <BarList
            data={energyBars}
            color="amber"
            className="mt-2"
          />
          {efficiency?.vs_typical && (
            <Text className="text-xs mt-3" style={{ color: "var(--color-grafana-text-secondary)" }}>
              {efficiency.vs_typical.energy_pct > 0
                ? `${efficiency.vs_typical.energy_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.energy_pct)}% below typical`}
            </Text>
          )}
        </Card>

        <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
          <Title>Carbon Intensity vs SA Benchmarks</Title>
          <Text className="mb-3" style={{ color: "var(--color-grafana-text-secondary)" }}>kg CO2 per sqm per year</Text>
          <BarList
            data={carbonBars}
            color="green"
            className="mt-2"
          />
          {efficiency?.vs_typical && (
            <Text className="text-xs mt-3" style={{ color: "var(--color-grafana-text-secondary)" }}>
              {efficiency.vs_typical.carbon_pct > 0
                ? `${efficiency.vs_typical.carbon_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.carbon_pct)}% below typical`}
            </Text>
          )}
        </Card>
      </Grid>

      {/* Green Star Tracker */}
      <Card className="panel" style={{ border: "1px solid var(--color-grafana-border)" }}>
        <Flex justifyContent="between" alignItems="center" className="mb-4">
          <div>
            <Title>Green Star SA Self-Assessment</Title>
            <Text style={{ color: "var(--color-grafana-text-secondary)" }}>{greenStar?.tool_version ?? 'Green Star SA Office v1.1'}</Text>
          </div>
          <div className="text-right">
            <Badge color="violet" size="lg">
              {greenStar?.estimated_star_rating ?? '—'}
            </Badge>
            <Text className="text-xs mt-1" style={{ color: "var(--color-grafana-text-secondary)" }}>
              Target: {greenStar?.target_rating ?? '5-Star'}
            </Text>
          </div>
        </Flex>

        <Grid className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(greenStar?.categories || []).map(cat => {
            const pct = cat.max_points > 0
              ? Math.round((cat.achieved_points / cat.max_points) * 100)
              : 0;
            const barColor = pct >= 75 ? 'var(--color-sentinel-green)' : pct >= 50 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-red)';
            const targetPct = cat.max_points > 0 && cat.target_points > 0
              ? Math.round((cat.target_points / cat.max_points) * 100)
              : 0;

            return (
              <Card key={cat.category_id} className="panel p-3" style={{ border: "1px solid var(--color-grafana-border)" }}>
                {/* Header: category name + code */}
                <Flex justifyContent="between" alignItems="center" className="mb-2">
                  <Text className="font-semibold text-sm">{cat.name}</Text>
                  <Text className="text-xs font-mono" style={{ color: "var(--color-grafana-text-disabled)" }}>{cat.category_id}</Text>
                </Flex>

                {/* Grafana-style stat: large achieved / max */}
                <div className="text-center my-2">
                  <span style={{ fontSize: '1.75rem', fontWeight: 700, color: barColor, lineHeight: 1 }}>
                    {cat.achieved_points}
                  </span>
                  <span style={{ fontSize: '1rem', fontWeight: 400, color: 'var(--color-grafana-text-disabled)' }}>
                    {' '}/ {cat.max_points}
                  </span>
                </div>

                {/* Gauge bar with target marker */}
                <div className="relative mt-1" style={{ height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.08)' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${pct}%`,
                      minWidth: 2,
                      borderRadius: 4,
                      background: barColor,
                      transition: 'width 0.6s ease',
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

                {/* Footer: target + percentage */}
                <Flex justifyContent="between" className="mt-1.5">
                  <Text className="text-xs" style={{ color: "var(--color-grafana-text-secondary)" }}>
                    {cat.target_points > 0 ? `Target: ${cat.target_points} pts` : '\u00A0'}
                  </Text>
                  <Text className="text-xs font-mono" style={{ color: "var(--color-grafana-text-disabled)" }}>
                    {pct}%
                  </Text>
                </Flex>

                {cat.notes && (
                  <Text className="text-xs mt-1 line-clamp-2" style={{ color: "var(--color-grafana-text-disabled)" }}>
                    {cat.notes}
                  </Text>
                )}
              </Card>
            );
          })}
        </Grid>

        {greenStar && (
          <Flex justifyContent="end" alignItems="baseline" className="mt-4 gap-2">
            <Text className="text-sm" style={{ color: "var(--color-grafana-text-secondary)" }}>Total:</Text>
            <span style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-grafana-text-primary)' }}>
              {greenStar.total_achieved}
            </span>
            <span style={{ fontSize: '0.875rem', color: 'var(--color-grafana-text-disabled)' }}>
              / {greenStar.total_max} pts
            </span>
            {greenStar.total_target > 0 && (
              <Text className="text-sm" style={{ color: "var(--color-grafana-text-secondary)" }}>
                (target: {greenStar.total_target})
              </Text>
            )}
          </Flex>
        )}
      </Card>
    </div>
  );
}

export default SustainabilityDashboard;
