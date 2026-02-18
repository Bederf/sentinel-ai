/**
 * Health Trend Chart
 *
 * Shows health score trend over time with line chart.
 */

import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { systemApi } from '@/lib/api';

export function HealthTrendChart() {
  const [chartData, setChartData] = useState<any[]>([]);
  const [selectedRange, setSelectedRange] = useState<'24h' | '7d' | '30d'>('7d');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTrend = async () => {
      try {
        setLoading(true);
        const data = await systemApi.getHealthHistory(selectedRange);

        // Format data for chart
        const formatted = (data.snapshots || []).map((s: any, i: number) => ({
          time: new Date(s.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          score: s.overall_score,
          index: i,
        }));

        setChartData(formatted);
      } catch (err) {
        console.error('Failed to fetch trend:', err);
        setChartData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchTrend();
  }, [selectedRange]);

  const ranges: Array<'24h' | '7d' | '30d'> = ['24h', '7d', '30d'];

  return (
    <div
      className="rounded-lg p-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h3
          className="text-sm font-medium"
          style={{ color: 'var(--color-sentinel-text-primary)' }}
        >
          Health Score Trend
        </h3>

        {/* Range selector */}
        <div className="flex gap-2">
          {ranges.map((range) => (
            <button
              key={range}
              onClick={() => setSelectedRange(range)}
              className="px-3 py-1 rounded text-xs font-medium transition-colors"
              style={{
                background: selectedRange === range ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-bg-secondary)',
                color: selectedRange === range ? 'white' : 'var(--color-sentinel-text-secondary)',
              }}
            >
              {range === '24h' ? '24H' : range === '7d' ? '7D' : '30D'}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading trend data...
          </span>
        </div>
      ) : chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-sentinel-border)"
            />
            <XAxis
              dataKey="time"
              stroke="var(--color-sentinel-text-secondary)"
              style={{ fontSize: '12px' }}
              interval={Math.floor(chartData.length / 6)}
            />
            <YAxis
              stroke="var(--color-sentinel-text-secondary)"
              style={{ fontSize: '12px' }}
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--color-sentinel-border)',
                borderRadius: '4px',
                color: 'var(--color-sentinel-text-primary)',
              }}
              formatter={(value) => [`${value}%`, 'Score']}
            />
            <Legend
              wrapperStyle={{
                color: 'var(--color-sentinel-text-secondary)',
                fontSize: '12px',
              }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="var(--color-sentinel-blue)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Health Score"
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-64 flex items-center justify-center">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No trend data available
          </span>
        </div>
      )}

      {/* Summary */}
      <div
        className="mt-4 pt-4 border-t"
        style={{ borderColor: 'var(--color-sentinel-border)' }}
      >
        <p
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          Data refreshes every 5 minutes. Historical data retained for 90 days.
        </p>
      </div>
    </div>
  );
}
