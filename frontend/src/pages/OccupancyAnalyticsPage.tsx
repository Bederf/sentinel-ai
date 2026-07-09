/**
 * OCCUPANCY ANALYTICS PAGE (Phase 5.1)
 *
 * Displays occupancy trends, zone utilization, and peak hour analysis
 * for the building across multiple time horizons.
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useModules } from '@/contexts/ModuleHooks';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Panel } from '@/components/Panel';
import { KPICard } from '@/components/KPICard';
import { AlertCircle, Activity, Clock, Users, TrendingUp } from 'lucide-react';
import { authorizedFetch } from '@/lib/api/client';
import { StatusBadge } from '@/components/StatusBadge';
import type { StatusKey } from '@/components/StatusBadge';

interface OccupancyTrendData {
  site_id: string;
  days: number;
  timestamp: string;
  hours: number[];
  zones: {
    office: number[];
    meeting: number[];
    common: number[];
    utility: number[];
    entry: number[];
  };
  daily_pattern: {
    peak_hours: number[];
    offpeak_hours: number[];
    peak_avg_occupancy: number;
    offpeak_avg_occupancy: number;
    peak_hours_text: string;
  };
}

interface ZoneUtilizationData {
  site_id: string;
  timestamp: string;
  zones: Array<{
    zone_id: string;
    zone_name: string;
    floor: number;
    max_occupancy: number;
    current_occupancy: number;
    utilization_percent: number;
    status: 'empty' | 'normal' | 'crowded' | 'over_capacity';
  }>;
  total_occupancy: number;
  average_utilization_percent: number;
}

interface PeakHoursData {
  site_id: string;
  timestamp: string;
  peak_hours: number[];
  offpeak_hours: number[];
  peak_occupancy_avg: number;
  offpeak_occupancy_avg: number;
  occupancy_differential: number;
  peak_hours_text: string;
  recommendations: string[];
}

interface OccupancyAnalyticsPageProps {
  siteId?: string;
}

export function OccupancyAnalyticsPage({ siteId: propSiteId }: OccupancyAnalyticsPageProps) {
  const { siteId: contextSiteId } = useModules();
  const siteId = propSiteId || contextSiteId || '';
  const [days, setDays] = useState<1 | 7 | 30>(1);

  const simulatedHour = new Date().getHours();
  const isSimulationRunning = false;

  // Fetch occupancy trend
  const { data: trendData, isLoading: trendLoading } = useQuery<OccupancyTrendData>({
    queryKey: ['occupancy-trend', siteId, days],
    queryFn: async () => {
      const response = await authorizedFetch(`/api/occupancy/analytics/hourly-trend?site_id=${siteId}&days=${days}`);
      if (!response.ok) throw new Error('Failed to fetch occupancy trend');
      return response.json();
    },
  });

  // Fetch zone utilization
  const { data: utilizationData, isLoading: utilizationLoading } = useQuery<ZoneUtilizationData>({
    queryKey: ['zone-utilization', siteId],
    queryFn: async () => {
      const response = await authorizedFetch(`/api/occupancy/analytics/zone-utilization?site_id=${siteId}`);
      if (!response.ok) throw new Error('Failed to fetch zone utilization');
      return response.json();
    },
  });

  // Fetch peak hours analysis
  const { data: peakHoursData, isLoading: peakHoursLoading } = useQuery<PeakHoursData>({
    queryKey: ['peak-hours', siteId],
    queryFn: async () => {
      const response = await authorizedFetch(`/api/occupancy/analytics/peak-hours?site_id=${siteId}`);
      if (!response.ok) throw new Error('Failed to fetch peak hours');
      return response.json();
    },
  });

  // Transform trend data for line chart
  const chartData = useMemo(() => {
    if (!trendData) return [];

    const hours = trendData.hours ?? [];
    const zones = trendData.zones ?? { office: [], meeting: [], common: [], utility: [], entry: [] };

    return hours.map((hour, index) => {
      return {
        hour: `${hour}:00`,
        office: zones.office[index] ?? 0,
        meeting: zones.meeting[index] ?? 0,
        common: zones.common[index] ?? 0,
        utility: zones.utility[index] ?? 0,
        entry: zones.entry[index] ?? 0,
      };
    });
  }, [trendData]);

  // Calculate average occupancy and get current hour occupancy
  const { averageOccupancy, currentHourOccupancy } = useMemo(() => {
    if (!trendData) return { averageOccupancy: 0, currentHourOccupancy: 0 };

    const hours = trendData.hours ?? [];
    const zones = trendData.zones ?? { office: [], meeting: [], common: [], utility: [], entry: [] };

    const allValues = [
      ...zones.office,
      ...zones.meeting,
      ...zones.common,
      ...zones.utility,
      ...zones.entry,
    ];
    const avg = allValues.length ? Math.round(allValues.reduce((a, b) => a + b, 0) / allValues.length) : 0;

    // Get current hour occupancy from live data
    let currentOccupancy = avg;
    if (simulatedHour !== undefined) {
      const hourIndex = hours.indexOf(simulatedHour);
      if (hourIndex !== -1) {
        const hourValues = [
          zones.office[hourIndex] ?? 0,
          zones.meeting[hourIndex] ?? 0,
          zones.common[hourIndex] ?? 0,
          zones.utility[hourIndex] ?? 0,
          zones.entry[hourIndex] ?? 0,
        ];
        currentOccupancy = Math.round(hourValues.reduce((a, b) => a + b, 0) / hourValues.length);
      }
    }

    return { averageOccupancy: avg, currentHourOccupancy: currentOccupancy };
  }, [trendData, simulatedHour]);

  const isLoading = trendLoading || utilizationLoading || peakHoursLoading;

  const zoneBarColor = (status: string) => {
    if (status === 'empty')   return 'var(--color-sentinel-green)';
    if (status === 'normal')  return 'var(--color-sentinel-blue)';
    if (status === 'crowded') return 'var(--color-sentinel-amber)';
    return 'var(--color-sentinel-red)';
  };

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="space-y-6 p-4 md:p-6">

        {/* Header + time range filter */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Occupancy Analytics
            </h1>
            <p className="text-sm mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Building-wide occupancy trends, zone utilization, and peak hour analysis.
            </p>
          </div>
          <div
            className="flex gap-1 p-1 rounded self-start sm:self-auto"
            style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
          >
            {([1, 7, 30] as const).map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className="px-3 py-1.5 rounded text-xs font-medium transition-colors"
                style={{
                  background: days === d ? "var(--color-sentinel-blue)" : "transparent",
                  color: days === d ? "#fff" : "var(--color-sentinel-text-secondary)",
                }}
              >
                {d === 1 ? '24 Hours' : `${d} Days`}
              </button>
            ))}
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <KPICard
            title={isSimulationRunning ? 'Live Occupancy' : 'Avg Occupancy'}
            value={`${isSimulationRunning ? currentHourOccupancy : averageOccupancy}%`}
            icon={<Activity className="h-5 w-5" />}
            accentColor="blue"
          />
          <KPICard
            title="Peak Hours"
            value={`${peakHoursData?.peak_hours.length ?? 0}h`}
            icon={<Clock className="h-5 w-5" />}
            accentColor="orange"
          />
          <KPICard
            title="Current Total"
            value={utilizationData?.total_occupancy ?? 0}
            icon={<Users className="h-5 w-5" />}
            accentColor="green"
          />
          <KPICard
            title="Differential"
            value={`${peakHoursData?.occupancy_differential ?? 0}%`}
            icon={<TrendingUp className="h-5 w-5" />}
            accentColor="purple"
          />
        </div>

        {/* Occupancy Trend Chart */}
        <Panel
          header={{
            icon: <Activity className="h-4 w-4" />,
            title: "Occupancy Trend",
            accentColor: "var(--color-sentinel-blue)",
          }}
        >
          <div className="p-4 pb-6">
            <p className="text-xs mb-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              24-hour occupancy pattern by zone type.
            </p>
            {isLoading ? (
              <div className="h-80 flex items-center justify-center text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                Loading chart data…
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={360}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-sentinel-border)" />
                  <XAxis dataKey="hour" tick={{ fontSize: 11 }} stroke="var(--color-sentinel-text-secondary)" />
                  <YAxis label={{ value: 'Occupancy %', angle: -90, position: 'insideLeft', fontSize: 11 }} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value) => `${value}%`}
                    contentStyle={{ backgroundColor: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)' }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="office"  stroke="var(--color-sentinel-blue)"   strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="meeting" stroke="var(--color-sentinel-purple)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="common"  stroke="var(--color-sentinel-green)"  strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="utility" stroke="var(--color-sentinel-amber)"  strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="entry"   stroke="var(--color-sentinel-red)"    strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>

        {/* Peak Hours Analysis */}
        {peakHoursData && (
          <Panel
            header={{
              icon: <Clock className="h-4 w-4" />,
              title: "Peak Hours Analysis",
              accentColor: "var(--color-sentinel-amber)",
            }}
          >
            <div className="p-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { label: "Peak Hours", value: peakHoursData.peak_hours_text, sub: `${peakHoursData.peak_occupancy_avg.toFixed(1)}% avg occupancy` },
                  { label: "Offpeak Hours", value: `${peakHoursData.offpeak_hours.length}h remaining`, sub: `${peakHoursData.offpeak_occupancy_avg.toFixed(1)}% avg occupancy` },
                  { label: "Differential", value: `${peakHoursData.occupancy_differential.toFixed(1)}%`, sub: "More during peak" },
                ].map(({ label, value, sub }) => (
                  <div key={label}>
                    <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>{label}</p>
                    <p className="text-2xl font-bold mt-1" style={{ color: "var(--color-sentinel-text-primary)" }}>{value}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>{sub}</p>
                  </div>
                ))}
              </div>

              <div className="pt-4" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-amber)" }} />
                  <div>
                    <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      Optimization Recommendations
                    </p>
                    <ul className="mt-2 space-y-1.5">
                      {peakHoursData.recommendations.map((rec, i) => (
                        <li key={i} className="text-sm flex items-start gap-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          <span style={{ color: "var(--color-sentinel-amber)" }}>•</span>
                          {rec}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </Panel>
        )}

        {/* Zone Utilization */}
        {utilizationData && (
          <Panel
            header={{
              icon: <Users className="h-4 w-4" />,
              title: "Zone Utilization",
              accentColor: "var(--color-sentinel-blue)",
            }}
          >
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {utilizationData.zones.map((zone) => (
                <div
                  key={zone.zone_id}
                  className="rounded-lg p-4"
                  style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
                >
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{zone.zone_name}</p>
                      <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>Floor {zone.floor}</p>
                    </div>
                    <StatusBadge status={zone.status as StatusKey} />
                  </div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="tabular-nums" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {zone.current_occupancy} / {zone.max_occupancy}
                    </span>
                    <span className="font-medium tabular-nums" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {zone.utilization_percent.toFixed(0)}%
                    </span>
                  </div>
                  <div
                    className="w-full rounded-full h-1.5 overflow-hidden"
                    style={{ background: "var(--color-sentinel-border)" }}
                  >
                    <div
                      className="h-full transition-all"
                      style={{
                        width: `${Math.min(zone.utilization_percent, 100)}%`,
                        background: zoneBarColor(zone.status),
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}

      </div>
    </div>
  );
}
