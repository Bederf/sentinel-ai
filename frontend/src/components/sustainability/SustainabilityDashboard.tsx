/**
 * Sustainability & ESG Dashboard - Bolt-on Module
 *
 * Displays carbon emissions, efficiency metrics, and Green Star SA tracker.
 * Derives all data from existing Energy module consumption data.
 */

import { useState, useEffect, useCallback } from 'react';
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
} from '@tremor/react';
import { sustainabilityApi } from '../../lib/sustainabilityApi';
import type {
  SustainabilitySummary,
  EmissionsHistory,
  EfficiencyMetrics,
  GreenStarAssessment,
} from '../../lib/sustainabilityApi';

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
  siteId,
  enabledModules: _enabledModules = ['sustainability'],
}: SustainabilityDashboardProps) {
  const [summary, setSummary] = useState<SustainabilitySummary | null>(null);
  const [history, setHistory] = useState<EmissionsHistory | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyMetrics | null>(null);
  const [greenStar, setGreenStar] = useState<GreenStarAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const currentSiteId = siteId || 'site-002'; // Default to site-002 if not provided
      const [s, h, e, g] = await Promise.all([
        sustainabilityApi.fetchSummary(currentSiteId),
        sustainabilityApi.fetchEmissions(currentSiteId, 12),
        sustainabilityApi.fetchEfficiency(currentSiteId),
        sustainabilityApi.fetchGreenStar(currentSiteId),
      ]);
      setSummary(s);
      setHistory(h);
      setEfficiency(e);
      setGreenStar(g);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sustainability data');
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading && !summary) {
    return (
      <Card>
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-1/3 mb-4" />
          <div className="h-64 bg-gray-100 rounded" />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
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
    <div className="space-y-4">
      {/* KPI Row */}
      <Grid numItems={2} numItemsLg={4} className="gap-4">
        <Card decoration="top" decorationColor="emerald">
          <Text>Total CO2 YTD</Text>
          <Metric>{summary?.ytd.total_co2_tonnes.toFixed(1) ?? '—'} t</Metric>
          <Flex className="mt-2">
            <Badge color={trendColor} size="xs">{trendLabel}</Badge>
            <Text className="text-xs text-gray-500">
              Target: -{summary?.target_reduction_pct ?? 10}% YoY
            </Text>
          </Flex>
        </Card>

        <Card decoration="top" decorationColor="blue">
          <Text>Carbon Intensity</Text>
          <Metric>
            {summary?.carbon_intensity_kg_per_sqm
              ? summary.carbon_intensity_kg_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kg/sqm</span>
          </Metric>
          <Text className="text-xs text-gray-500 mt-2">Current month</Text>
        </Card>

        <Card decoration="top" decorationColor="amber">
          <Text>Energy Intensity</Text>
          <Metric>
            {summary?.energy_intensity_kwh_per_sqm
              ? summary.energy_intensity_kwh_per_sqm.toFixed(1)
              : '—'}{' '}
            <span className="text-sm font-normal">kWh/sqm</span>
          </Metric>
          <Text className="text-xs text-gray-500 mt-2">Current month</Text>
        </Card>

        <Card decoration="top" decorationColor="violet">
          <Text>Green Star Progress</Text>
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
      <Card>
        <Title>Monthly Emissions by Scope (tonnes CO2)</Title>
        <Text className="text-gray-500 mb-4">
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
          <Text className="text-gray-400">No emissions data available</Text>
        )}
      </Card>

      {/* Efficiency vs Benchmarks */}
      <Grid numItems={1} numItemsLg={2} className="gap-4">
        <Card>
          <Title>Energy Intensity vs SA Benchmarks</Title>
          <Text className="text-gray-500 mb-3">kWh per sqm per year</Text>
          <BarList data={energyBars} color="amber" className="mt-2" />
          {efficiency?.vs_typical && (
            <Text className="text-xs mt-3 text-gray-500">
              {efficiency.vs_typical.energy_pct > 0
                ? `${efficiency.vs_typical.energy_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.energy_pct)}% below typical`}
            </Text>
          )}
        </Card>

        <Card>
          <Title>Carbon Intensity vs SA Benchmarks</Title>
          <Text className="text-gray-500 mb-3">kg CO2 per sqm per year</Text>
          <BarList data={carbonBars} color="emerald" className="mt-2" />
          {efficiency?.vs_typical && (
            <Text className="text-xs mt-3 text-gray-500">
              {efficiency.vs_typical.carbon_pct > 0
                ? `${efficiency.vs_typical.carbon_pct}% above typical`
                : `${Math.abs(efficiency.vs_typical.carbon_pct)}% below typical`}
            </Text>
          )}
        </Card>
      </Grid>

      {/* Green Star Tracker */}
      <Card>
        <Flex justifyContent="between" alignItems="center" className="mb-4">
          <div>
            <Title>Green Star SA Self-Assessment</Title>
            <Text className="text-gray-500">{greenStar?.tool_version ?? 'Green Star SA Office v1.1'}</Text>
          </div>
          <div className="text-right">
            <Badge color="violet" size="lg">
              {greenStar?.estimated_star_rating ?? '—'}
            </Badge>
            <Text className="text-xs text-gray-500 mt-1">
              Target: {greenStar?.target_rating ?? '5-Star'}
            </Text>
          </div>
        </Flex>

        <Grid numItems={1} numItemsSm={2} numItemsLg={3} className="gap-3">
          {(greenStar?.categories || []).map(cat => {
            const pct = cat.max_points > 0
              ? Math.round((cat.achieved_points / cat.max_points) * 100)
              : 0;
            const color = pct >= 75 ? 'emerald' : pct >= 50 ? 'amber' : 'red';

            return (
              <Card key={cat.category_id} className="p-3">
                <Flex justifyContent="between" alignItems="center">
                  <div>
                    <Text className="font-semibold text-sm">{cat.name}</Text>
                    <Text className="text-xs text-gray-400">{cat.category_id}</Text>
                  </div>
                  <Badge color={color} size="xs">
                    {cat.achieved_points}/{cat.max_points}
                  </Badge>
                </Flex>
                <ProgressBar value={pct} color={color} className="mt-2" />
                {cat.target_points > 0 && (
                  <Text className="text-xs text-gray-500 mt-1">
                    Target: {cat.target_points} pts
                  </Text>
                )}
                {cat.notes && (
                  <Text className="text-xs text-gray-400 mt-1 line-clamp-2">
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
                <span className="text-gray-500"> (target: {greenStar.total_target})</span>
              )}
            </Text>
          </Flex>
        )}
      </Card>
    </div>
  );
}

export default SustainabilityDashboard;
