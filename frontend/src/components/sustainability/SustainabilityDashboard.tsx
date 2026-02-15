/**
 * Sustainability & ESG Dashboard - Bolt-on Module
 *
 * Displays carbon emissions, efficiency metrics, and Green Star SA tracker.
 * Derives all data from existing Energy module consumption data.
 */

import { useState, useEffect, useCallback } from 'react';
import { Leaf } from 'lucide-react';
import {
  Card,
  Title,
  Text,
  Grid,
  Badge,
  Flex,
  BarChart,
  ProgressBar,
  Metric,
  BarList,
  Select,
  SelectItem,
} from '@tremor/react';
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
  enabledModules: _enabledModules = ['sustainability'],
}: SustainabilityDashboardProps) {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');
  const [summary, setSummary] = useState<SustainabilitySummary | null>(null);
  const [history, setHistory] = useState<EmissionsHistory | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyMetrics | null>(null);
  const [greenStar, setGreenStar] = useState<GreenStarAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [sitesLoading, setSitesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch sites on mount
  useEffect(() => {
    api.getSites()
      .then((fetchedSites) => {
        setSites(fetchedSites);
        if (fetchedSites.length > 0) {
          const initialSite = _externalSiteId || fetchedSites[0].id;
          setSelectedSiteId(initialSite);
        }
      })
      .catch(() => {
        // Fallback to site-002 if API fails
        setSites([{ id: 'site-002', name: 'Sandton City Office Tower', location: 'Sandton', region: 'Gauteng', type: 'commercial', equipment_count: 0, alert_count: 0, status: 'normal' }]);
        setSelectedSiteId(_externalSiteId || 'site-002');
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
        <Text className="text-red-500 mt-2">{error}</Text>
      </Card>
    );
  }

  const trendColor = summary?.trend === 'improving' ? 'emerald'
    : summary?.trend === 'worsening' ? 'red' : 'gray';
  const trendLabel = summary?.trend === 'improving' ? 'Improving'
    : summary?.trend === 'worsening' ? 'Worsening' : 'Stable';

  // Chart data: monthly emissions stacked by scope
  const chartData = (history?.data || []).map(d => ({
    month: d.month.slice(5), // MM only for compact labels
    'Scope 1 (Diesel)': Math.round(d.scope1_kg_co2 / 1000 * 100) / 100,
    'Scope 2 (Grid)': Math.round(d.scope2_kg_co2 / 1000 * 100) / 100,
    'Scope 3 (Other)': Math.round(d.scope3_kg_co2 / 1000 * 100) / 100,
  }));

  // Efficiency benchmark bars
  const energyBars = efficiency ? [
    { name: 'Your Site', value: Math.round(efficiency.energy_intensity_kwh_per_sqm_yr) },
    { name: 'SA Typical', value: efficiency.benchmarks?.energy_typical ?? 170 },
    { name: 'SA Efficient', value: efficiency.benchmarks?.energy_efficient ?? 120 },
  ] : [];

  const carbonBars = efficiency ? [
    { name: 'Your Site', value: Math.round(efficiency.carbon_intensity_kg_per_sqm_yr) },
    { name: 'SA Typical', value: efficiency.benchmarks?.carbon_typical ?? 85 },
    { name: 'SA Efficient', value: efficiency.benchmarks?.carbon_efficient ?? 55 },
  ] : [];

  return (
    <div className="space-y-6 p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {/* Header with Building Selector */}
      <div
        className="glass-panel rounded-lg p-4 md:p-5 flex items-center justify-between flex-wrap gap-3"
        style={{ border: "1px solid var(--glass-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: 'rgba(16, 185, 129, 0.15)' }}
          >
            <Leaf className="h-5 w-5" style={{ color: 'var(--color-sentinel-emerald)' }} />
          </div>
          <div>
            <h2
              className="text-lg font-semibold"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Sustainability & ESG
            </h2>
            <p
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              Carbon emissions, efficiency metrics, and Green Star SA tracker
            </p>
          </div>
        </div>

        {/* Building Selector */}
        {!sitesLoading && sites.length > 0 && (
          <Select
            value={selectedSiteId}
            onValueChange={setSelectedSiteId}
            className="w-56"
          >
            {sites.map((site) => (
              <SelectItem key={site.id} value={site.id}>
                {site.name}
              </SelectItem>
            ))}
          </Select>
        )}
      </div>

      {/* KPI Row */}
      <Grid className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Total CO2 YTD</Text>
          <Metric>{summary?.ytd.total_co2_tonnes.toFixed(1) ?? '—'} t</Metric>
          <Flex className="mt-2">
            <Badge color={trendColor} size="xs">{trendLabel}</Badge>
            <Text className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Target: -{summary?.target_reduction_pct ?? 10}% YoY
            </Text>
          </Flex>
        </Card>

        <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Carbon Intensity</Text>
          <Metric>
            {summary?.carbon_intensity_kg_per_sqm
              ? summary.carbon_intensity_kg_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kg/sqm</span>
          </Metric>
          <Text className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>Current month</Text>
        </Card>

        <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Energy Intensity</Text>
          <Metric>
            {summary?.energy_intensity_kwh_per_sqm
              ? summary.energy_intensity_kwh_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kWh/sqm</span>
          </Metric>
          <Text className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>Current month</Text>
        </Card>

        <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
          <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>Green Star Progress</Text>
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
      </Grid>

      {/* Emissions Chart */}
      <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
        <Title>Monthly Emissions by Scope (tonnes CO2)</Title>
        <Text className="mb-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Scope 1: Diesel generators | Scope 2: Grid electricity | Scope 3: Water, waste, commuting
        </Text>
        {chartData.length > 0 ? (
          <BarChart
            data={chartData}
            index="month"
            categories={['Scope 1 (Diesel)', 'Scope 2 (Grid)', 'Scope 3 (Other)']}
            colors={['orange', 'blue', 'gray']}
            stack
            yAxisWidth={56}
            className="h-72"
          />
        ) : (
          <Text style={{ color: "var(--color-sentinel-text-disabled)" }}>No emissions data available</Text>
        )}
      </Card>

      {/* Efficiency vs Benchmarks */}
      <Grid className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
          <Title>Energy Intensity vs SA Benchmarks</Title>
          <Text className="mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>kWh per sqm per year</Text>
          <BarList data={energyBars} color="amber" className="mt-2" />
          {efficiency?.vs_typical && (
            <Text className="text-xs mt-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {efficiency.vs_typical.energy_pct > 0
                ? `${efficiency.vs_typical.energy_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.energy_pct)}% below typical`}
            </Text>
          )}
        </Card>

        <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
          <Title>Carbon Intensity vs SA Benchmarks</Title>
          <Text className="mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>kg CO2 per sqm per year</Text>
          <BarList data={carbonBars} color="emerald" className="mt-2" />
          {efficiency?.vs_typical && (
            <Text className="text-xs mt-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {efficiency.vs_typical.carbon_pct > 0
                ? `${efficiency.vs_typical.carbon_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.carbon_pct)}% below typical`}
            </Text>
          )}
        </Card>
      </Grid>

      {/* Green Star Tracker */}
      <Card className="glass-panel" style={{ border: "1px solid var(--glass-border)" }}>
        <Flex justifyContent="between" alignItems="center" className="mb-4">
          <div>
            <Title>Green Star SA Self-Assessment</Title>
            <Text style={{ color: "var(--color-sentinel-text-secondary)" }}>{greenStar?.tool_version ?? 'Green Star SA Office v1.1'}</Text>
          </div>
          <div className="text-right">
            <Badge color="violet" size="lg">
              {greenStar?.estimated_star_rating ?? '—'}
            </Badge>
            <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Target: {greenStar?.target_rating ?? '5-Star'}
            </Text>
          </div>
        </Flex>

        <Grid className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(greenStar?.categories || []).map(cat => {
            const pct = cat.max_points > 0
              ? Math.round((cat.achieved_points / cat.max_points) * 100)
              : 0;
            const color = pct >= 75 ? 'emerald' : pct >= 50 ? 'amber' : 'red';

            return (
              <Card key={cat.category_id} className="glass-panel p-3" style={{ border: "1px solid var(--glass-border)" }}>
                <Flex justifyContent="between" alignItems="center">
                  <div>
                    <Text className="font-semibold text-sm">{cat.name}</Text>
                    <Text className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{cat.category_id}</Text>
                  </div>
                  <Badge color={color} size="xs">
                    {cat.achieved_points}/{cat.max_points}
                  </Badge>
                </Flex>
                <ProgressBar value={pct} color={color} className="mt-2" />
                {cat.target_points > 0 && (
                  <Text className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Target: {cat.target_points} pts
                  </Text>
                )}
                {cat.notes && (
                  <Text className="text-xs mt-1 line-clamp-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    {cat.notes}
                  </Text>
                )}
              </Card>
            );
          })}
        </Grid>

        {greenStar && (
          <Flex justifyContent="end" className="mt-4">
            <Text className="text-sm">
              Total: <span className="font-bold">{greenStar.total_achieved}</span>
              /{greenStar.total_max} pts
              {greenStar.total_target > 0 && (
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}> (target: {greenStar.total_target})</span>
              )}
            </Text>
          </Flex>
        )}
      </Card>
    </div>
  );
}

export default SustainabilityDashboard;
