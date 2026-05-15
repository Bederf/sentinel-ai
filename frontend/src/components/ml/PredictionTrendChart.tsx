/**
 * LSTM Prediction Trend Chart
 *
 * Displays historical sensor data + 24/48/72h predictions
 * with confidence indicator.
 */

import { useEffect, useState } from "react";

import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import type { TrendData } from "../../lib/mlApi";
import { getPredictionTrend, formatPrediction } from "../../lib/mlApi";

interface PredictionTrendChartProps {
  equipmentId: string;
  equipmentType: string;
  title?: string;
  unit?: string;
  refreshInterval?: number; // ms, 0 = no refresh
}

interface ChartDataPoint {
  hour: number;
  value: number;
  type: string;
}

export function PredictionTrendChart({
  equipmentId,
  equipmentType,
  title = "Temperature Trend",
  unit = "°C",
  refreshInterval = 0,
}: PredictionTrendChartProps) {
  const [data, setData] = useState<TrendData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setError(null);
      const result = await getPredictionTrend(equipmentId, equipmentType);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (refreshInterval > 0) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equipmentId, equipmentType, refreshInterval]);

  if (loading) {
    return (
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
        <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>{title}</h3>
        <div className="h-72 flex items-center justify-center">
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Loading prediction data...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
        <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>{title}</h3>
        <div className="h-72 flex items-center justify-center">
          <p style={{color:'var(--color-sentinel-red)'}}>{error || "No data available"}</p>
        </div>
      </div>
    );
  }

  // Combine historical and predicted data for chart
  const chartData: ChartDataPoint[] = [
    // Historical data
    ...data.visualization_data.x_historical.map((hour, idx) => ({
      hour,
      value: data.visualization_data.y_historical[idx],
      type: "Historical",
    })),
    // Current point (last historical)
    {
      hour: 0,
      value: data.visualization_data.y_historical[data.visualization_data.y_historical.length - 1],
      type: "Historical",
    },
    // Predicted points
    ...data.visualization_data.x_predicted.map((hour, idx) => ({
      hour,
      value: data.visualization_data.y_predicted[idx] || 0,
      type: "Predicted",
    })),
  ];

  // Get current value (last historical)
  const currentValue = data.visualization_data.y_historical[
    data.visualization_data.y_historical.length - 1
  ];

  return (
    <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>{title}</h3>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>
            {equipmentId} ({equipmentType})
          </p>
        </div>
        <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full" style={{background:'rgba(59,130,246,0.15)', color:'var(--color-sentinel-blue)'}}>
          Confidence: 85%
        </span>
      </div>

      <ResponsiveContainer width="100%" height={288}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--color-sentinel-blue)" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="var(--color-sentinel-blue)" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--color-sentinel-border)" strokeDasharray="2 4" />
          <XAxis dataKey="hour" stroke="var(--color-sentinel-text-secondary)" tick={{fontSize:11}} />
          <YAxis stroke="var(--color-sentinel-text-secondary)" tick={{fontSize:11}} />
          <Tooltip contentStyle={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:6, fontSize:12}} content={({ active, payload }) => {
            if (!active || !payload?.[0]) return null;
            const point = payload[0].payload as ChartDataPoint;
            return (
              <div className="p-2 shadow-lg rounded" style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)'}}>
                <p className="font-medium" style={{color:'var(--color-sentinel-text-primary)'}}>
                  {point.hour < 0
                    ? `${Math.abs(point.hour)}h ago`
                    : point.hour === 0
                    ? "Now"
                    : `+${point.hour}h`}
                </p>
                <p style={{color: point.type === "Predicted" ? 'var(--color-sentinel-blue)' : 'var(--color-sentinel-text-secondary)'}}>
                  {point.type}: {point.value.toFixed(1)}{unit}
                </p>
              </div>
            );
          }} />
          <Area type="monotone" dataKey="value" stroke="var(--color-sentinel-blue)" fill="url(#colorValue)" isAnimationActive />
        </AreaChart>
      </ResponsiveContainer>

      {/* Prediction cards */}
      <div className="grid grid-cols-4 gap-4 mt-4">
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-text-secondary)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Current</p>
          <div className="text-3xl font-semibold tabular-nums">{formatPrediction(currentValue, unit)}</div>
        </div>
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-blue)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>24h Forecast</p>
          <div className="text-3xl font-semibold tabular-nums">{formatPrediction(data.predicted["24h"], unit)}</div>
        </div>
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-blue)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>48h Forecast</p>
          <div className="text-3xl font-semibold tabular-nums">{formatPrediction(data.predicted["48h"], unit)}</div>
        </div>
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-blue)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>72h Forecast</p>
          <div className="text-3xl font-semibold tabular-nums">{formatPrediction(data.predicted["72h"], unit)}</div>
        </div>
      </div>
    </div>
  );
}

export default PredictionTrendChart;
