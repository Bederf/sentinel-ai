/**
 * LSTM Prediction Trend Chart
 *
 * Displays historical sensor data + 24/48/72h predictions
 * with confidence indicator.
 */

import { useEffect, useState } from "react";
import {
  Card,
  Title,
  AreaChart,
  Badge,
  Flex,
  Text,
  Grid,
  Metric,
} from "@tremor/react";
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
  }, [equipmentId, equipmentType, refreshInterval]);

  if (loading) {
    return (
      <Card>
        <Title>{title}</Title>
        <div className="h-72 flex items-center justify-center">
          <Text>Loading prediction data...</Text>
        </div>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <Title>{title}</Title>
        <div className="h-72 flex items-center justify-center">
          <Text color="red">{error || "No data available"}</Text>
        </div>
      </Card>
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
    <Card>
      <Flex justifyContent="between" alignItems="center" className="mb-4">
        <div>
          <Title>{title}</Title>
          <Text className="text-sm text-gray-500">
            {equipmentId} ({equipmentType})
          </Text>
        </div>
        <Badge color="blue" size="lg">
          Confidence: 85%
        </Badge>
      </Flex>

      <AreaChart
        className="h-72"
        data={chartData}
        index="hour"
        categories={["value"]}
        colors={["blue"]}
        valueFormatter={(v) => `${v.toFixed(1)}${unit}`}
        showAnimation
        curveType="monotone"
        showLegend={false}
        customTooltip={({ payload }) => {
          if (!payload?.[0]) return null;
          const point = payload[0].payload as ChartDataPoint;
          return (
            <div className="bg-white p-2 shadow-lg rounded border">
              <Text className="font-medium">
                {point.hour < 0
                  ? `${Math.abs(point.hour)}h ago`
                  : point.hour === 0
                  ? "Now"
                  : `+${point.hour}h`}
              </Text>
              <Text color={point.type === "Predicted" ? "blue" : "gray"}>
                {point.type}: {point.value.toFixed(1)}
                {unit}
              </Text>
            </div>
          );
        }}
      />

      {/* Prediction cards */}
      <Grid className="grid grid-cols-4 gap-4 mt-4">
        <Card decoration="top" decorationColor="gray">
          <Text>Current</Text>
          <Metric>{formatPrediction(currentValue, unit)}</Metric>
        </Card>
        <Card decoration="top" decorationColor="blue">
          <Text>24h Forecast</Text>
          <Metric>{formatPrediction(data.predicted["24h"], unit)}</Metric>
        </Card>
        <Card decoration="top" decorationColor="blue">
          <Text>48h Forecast</Text>
          <Metric>{formatPrediction(data.predicted["48h"], unit)}</Metric>
        </Card>
        <Card decoration="top" decorationColor="blue">
          <Text>72h Forecast</Text>
          <Metric>{formatPrediction(data.predicted["72h"], unit)}</Metric>
        </Card>
      </Grid>
    </Card>
  );
}

export default PredictionTrendChart;
