/**
 * OCCUPANCY ANALYTICS PAGE (Phase 5.1)
 *
 * Displays occupancy trends, zone utilization, and peak hour analysis
 * for the building across multiple time horizons.
 */

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSimulation } from '@/contexts/SimulationContext';
import { useModules } from '@/contexts/ModuleHooks';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Card } from '@/components/Card';
import { AlertCircle } from 'lucide-react';

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

export function OccupancyAnalyticsPage() {
  const { siteId: contextSiteId } = useModules();
  const [siteId] = useState(contextSiteId || '');
  const [days, setDays] = useState<1 | 7 | 30>(1);

  // Get simulation context
  const { running: isSimulationRunning, simulatedHour, daysSimulated } = useSimulation();

  // Fetch occupancy trend
  const { data: trendData, isLoading: trendLoading } = useQuery<OccupancyTrendData>({
    queryKey: ['occupancy-trend', siteId, days],
    queryFn: async () => {
      const response = await fetch(`/api/occupancy/analytics/hourly-trend?site_id=${siteId}&days=${days}`);
      if (!response.ok) throw new Error('Failed to fetch occupancy trend');
      return response.json();
    },
  });

  // Fetch zone utilization
  const { data: utilizationData, isLoading: utilizationLoading } = useQuery<ZoneUtilizationData>({
    queryKey: ['zone-utilization', siteId],
    queryFn: async () => {
      const response = await fetch(`/api/occupancy/analytics/zone-utilization?site_id=${siteId}`);
      if (!response.ok) throw new Error('Failed to fetch zone utilization');
      return response.json();
    },
  });

  // Fetch peak hours analysis
  const { data: peakHoursData, isLoading: peakHoursLoading } = useQuery<PeakHoursData>({
    queryKey: ['peak-hours', siteId],
    queryFn: async () => {
      const response = await fetch(`/api/occupancy/analytics/peak-hours?site_id=${siteId}`);
      if (!response.ok) throw new Error('Failed to fetch peak hours');
      return response.json();
    },
  });

  // Transform trend data for line chart
  const chartData = useMemo(() => {
    if (!trendData) return [];

    return trendData.hours.map((hour) => {
      const index = trendData.hours.indexOf(hour);
      return {
        hour: `${hour}:00`,
        office: trendData.zones.office[index] ?? 0,
        meeting: trendData.zones.meeting[index] ?? 0,
        common: trendData.zones.common[index] ?? 0,
        utility: trendData.zones.utility[index] ?? 0,
        entry: trendData.zones.entry[index] ?? 0,
      };
    });
  }, [trendData]);

  // Calculate average occupancy and get current hour occupancy
  const { averageOccupancy, currentHourOccupancy } = useMemo(() => {
    if (!trendData) return { averageOccupancy: 0, currentHourOccupancy: 0 };

    const allValues = [
      ...trendData.zones.office,
      ...trendData.zones.meeting,
      ...trendData.zones.common,
      ...trendData.zones.utility,
      ...trendData.zones.entry,
    ];
    const avg = Math.round(allValues.reduce((a, b) => a + b, 0) / allValues.length);

    // Get current hour occupancy from simulation if running
    let currentOccupancy = avg;
    if (isSimulationRunning && simulatedHour !== undefined) {
      const hourIndex = trendData.hours.indexOf(simulatedHour);
      if (hourIndex !== -1) {
        const hourValues = [
          trendData.zones.office[hourIndex] ?? 0,
          trendData.zones.meeting[hourIndex] ?? 0,
          trendData.zones.common[hourIndex] ?? 0,
          trendData.zones.utility[hourIndex] ?? 0,
          trendData.zones.entry[hourIndex] ?? 0,
        ];
        currentOccupancy = Math.round(hourValues.reduce((a, b) => a + b, 0) / hourValues.length);
      }
    }

    return { averageOccupancy: avg, currentHourOccupancy: currentOccupancy };
  }, [trendData, isSimulationRunning, simulatedHour]);

  const isLoading = trendLoading || utilizationLoading || peakHoursLoading;

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-4xl font-bold">Occupancy Analytics</h1>
              {isSimulationRunning && (
                <div className="px-3 py-1 rounded-full text-sm font-medium"
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: 'var(--color-sentinel-blue)',
                  }}
                >
                  🔴 Live • Hour {simulatedHour}:00 (Day {daysSimulated}/365)
                </div>
              )}
            </div>
            <p className="text-muted-foreground mt-2">
              {isSimulationRunning
                ? 'Real-time occupancy from 365-day simulation'
                : 'Building-wide occupancy trends, zone utilization, and peak hour analysis'
              }
            </p>
          </div>

          {/* Time Range Filter */}
          <div className="flex gap-2">
            <div className="flex gap-2 p-1 rounded" style={{ backgroundColor: 'var(--color-sentinel-bg-subtle)' }}>
              <button
                onClick={() => setDays(1)}
                className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                  days === 1 ? 'text-white' : 'opacity-60'
                }`}
                style={{
                  backgroundColor: days === 1 ? 'var(--color-primary)' : 'transparent',
                }}
              >
                24 Hours
              </button>
              <button
                onClick={() => setDays(7)}
                className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                  days === 7 ? 'text-white' : 'opacity-60'
                }`}
                style={{
                  backgroundColor: days === 7 ? 'var(--color-primary)' : 'transparent',
                }}
              >
                7 Days
              </button>
              <button
                onClick={() => setDays(30)}
                className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                  days === 30 ? 'text-white' : 'opacity-60'
                }`}
                style={{
                  backgroundColor: days === 30 ? 'var(--color-primary)' : 'transparent',
                }}
              >
                30 Days
              </button>
            </div>
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <div className="p-4">
              <p className="text-sm font-medium opacity-75">
                {isSimulationRunning ? 'Live Occupancy' : 'Avg Occupancy'}
              </p>
              <div className="text-3xl font-bold mt-2">
                {isSimulationRunning ? currentHourOccupancy : averageOccupancy}%
              </div>
              <p className="text-xs opacity-50 mt-2">
                {isSimulationRunning ? `Hour ${simulatedHour}:00` : 'Across all zones'}
              </p>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <p className="text-sm font-medium opacity-75">Peak Hours</p>
              <div className="text-3xl font-bold mt-2">{peakHoursData?.peak_hours.length ?? 0}h</div>
              <p className="text-xs opacity-50 mt-2">{peakHoursData?.peak_hours_text ?? 'N/A'}</p>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <p className="text-sm font-medium opacity-75">Current Total</p>
              <div className="text-3xl font-bold mt-2">{utilizationData?.total_occupancy ?? 0}</div>
              <p className="text-xs opacity-50 mt-2">People in building</p>
            </div>
          </Card>

          <Card>
            <div className="p-4">
              <p className="text-sm font-medium opacity-75">Differential</p>
              <div className="text-3xl font-bold mt-2">{peakHoursData?.occupancy_differential ?? 0}%</div>
              <p className="text-xs opacity-50 mt-2">Peak vs Offpeak</p>
            </div>
          </Card>
        </div>

        {/* Occupancy Trend Chart */}
        <Card>
          <div className="p-6 border-b border-opacity-20">
            <h2 className="text-lg font-semibold">Occupancy Trend</h2>
            <p className="text-sm opacity-75 mt-1">24-hour occupancy pattern by zone type</p>
          </div>
          <div className="p-6">
            {isLoading ? (
              <div className="h-80 flex items-center justify-center text-muted-foreground">
                Loading chart data...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" />
                  <YAxis label={{ value: 'Occupancy %', angle: -90, position: 'insideLeft' }} />
                  <Tooltip
                    formatter={(value) => `${value}%`}
                    contentStyle={{ backgroundColor: '#1e1e1e', border: '1px solid #333' }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="office" stroke="#3b82f6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="meeting" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="common" stroke="#10b981" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="utility" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="entry" stroke="#ef4444" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Peak Hours Analysis */}
        {peakHoursData && (
          <Card>
            <div className="p-6 border-b border-opacity-20">
              <h2 className="text-lg font-semibold">Peak Hours Analysis</h2>
              <p className="text-sm opacity-75 mt-1">Identified peak occupancy periods and recommendations</p>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Peak Hours</p>
                  <p className="text-2xl font-bold mt-1">{peakHoursData.peak_hours_text}</p>
                  <p className="text-sm text-muted-foreground mt-2">{peakHoursData.peak_occupancy_avg.toFixed(1)}% avg occupancy</p>
                </div>

                <div>
                  <p className="text-sm font-medium text-muted-foreground">Offpeak Hours</p>
                  <p className="text-2xl font-bold mt-1">{peakHoursData.offpeak_hours.length}h remaining</p>
                  <p className="text-sm text-muted-foreground mt-2">{peakHoursData.offpeak_occupancy_avg.toFixed(1)}% avg occupancy</p>
                </div>

                <div>
                  <p className="text-sm font-medium text-muted-foreground">Differential</p>
                  <p className="text-2xl font-bold mt-1">{peakHoursData.occupancy_differential.toFixed(1)}%</p>
                  <p className="text-sm text-muted-foreground mt-2">More during peak</p>
                </div>
              </div>

              {/* Recommendations */}
              <div className="mt-6 border-t pt-6">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-amber-500 mt-1 flex-shrink-0" />
                  <div>
                    <p className="font-medium">Optimization Recommendations</p>
                    <ul className="mt-3 space-y-2">
                      {peakHoursData.recommendations.map((rec, i) => (
                        <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                          <span className="text-amber-500 mt-1">•</span>
                          {rec}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Zone Utilization */}
        {utilizationData && (
          <Card>
            <div className="p-6 border-b border-opacity-20">
              <h2 className="text-lg font-semibold">Zone Utilization</h2>
              <p className="text-sm opacity-75 mt-1">Current occupancy as percentage of maximum capacity</p>
            </div>
            <div className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {utilizationData.zones.map((zone) => (
                  <div key={zone.zone_id} className="border rounded-lg p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <p className="font-medium">{zone.zone_name}</p>
                        <p className="text-xs text-muted-foreground">Floor {zone.floor}</p>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded ${
                        zone.status === 'empty' ? 'bg-green-100 text-green-800' :
                        zone.status === 'normal' ? 'bg-blue-100 text-blue-800' :
                        zone.status === 'crowded' ? 'bg-orange-100 text-orange-800' :
                        'bg-red-100 text-red-800'
                      }`}>
                        {zone.status}
                      </span>
                    </div>

                    <div className="mb-3">
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-muted-foreground">{zone.current_occupancy} / {zone.max_occupancy}</span>
                        <span className="font-medium">{zone.utilization_percent.toFixed(0)}%</span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full transition-all ${
                            zone.status === 'empty' ? 'bg-green-500' :
                            zone.status === 'normal' ? 'bg-blue-500' :
                            zone.status === 'crowded' ? 'bg-orange-500' :
                            'bg-red-500'
                          }`}
                          style={{ width: `${Math.min(zone.utilization_percent, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
