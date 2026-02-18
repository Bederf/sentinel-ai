/**
 * Uptime Metrics Card
 *
 * Shows uptime percentages for different time ranges (24h, 7d, 30d).
 */

import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { systemApi } from '@/lib/api';

export function UptimeMetricsCard() {
  const [metrics, setMetrics] = useState<any>(null);
  const [selectedRange, setSelectedRange] = useState<'24h' | '7d' | '30d'>('24h');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        setLoading(true);
        const data = await systemApi.getHealthHistory(selectedRange);
        setMetrics(data);
      } catch (err) {
        console.error('Failed to fetch uptime metrics:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchMetrics();
  }, [selectedRange]);

  const ranges: Array<'24h' | '7d' | '30d'> = ['24h', '7d', '30d'];
  const rangeLabels = {
    '24h': '24 Hours',
    '7d': '7 Days',
    '30d': '30 Days',
  };

  const uptimeData = [
    { range: '00:00-04:00', uptime: 100 },
    { range: '04:00-08:00', uptime: 98 },
    { range: '08:00-12:00', uptime: 99 },
    { range: '12:00-16:00', uptime: 100 },
    { range: '16:00-20:00', uptime: 97 },
    { range: '20:00-00:00', uptime: 100 },
  ];

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
          System Uptime
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
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Metrics Summary */}
      {metrics && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Uptime
            </span>
            <p className="text-xl font-bold mt-1" style={{ color: 'var(--color-sentinel-green)' }}>
              {metrics.metrics?.uptime_percentage?.toFixed(1)}%
            </p>
          </div>
          <div>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Avg Score
            </span>
            <p className="text-xl font-bold mt-1" style={{ color: 'var(--color-sentinel-blue)' }}>
              {metrics.metrics?.avg_score?.toFixed(0)}
            </p>
          </div>
          <div>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Trend
            </span>
            <p
              className="text-lg font-bold mt-1"
              style={{
                color:
                  metrics.metrics?.trend === 'improving'
                    ? 'var(--color-sentinel-green)'
                    : metrics.metrics?.trend === 'degrading'
                    ? 'var(--color-sentinel-red)'
                    : 'var(--color-sentinel-amber)',
              }}
            >
              {metrics.metrics?.trend}
            </p>
          </div>
        </div>
      )}

      {/* Chart */}
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading metrics...
          </span>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={uptimeData}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-sentinel-border)"
            />
            <XAxis
              dataKey="range"
              stroke="var(--color-sentinel-text-secondary)"
              style={{ fontSize: '12px' }}
            />
            <YAxis
              stroke="var(--color-sentinel-text-secondary)"
              style={{ fontSize: '12px' }}
              domain={[90, 100]}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--color-sentinel-border)',
                borderRadius: '4px',
                color: 'var(--color-sentinel-text-primary)',
              }}
            />
            <Bar dataKey="uptime" fill="var(--color-sentinel-green)" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
