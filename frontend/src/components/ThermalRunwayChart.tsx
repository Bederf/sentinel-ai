/**
 * ThermalRunwayChart Component - Building Comfort Visualization
 *
 * Shows temperature curves during load shedding with/without pre-cooling.
 * The "aha moment" visualization for Phase 10.
 *
 * Uses Recharts for consistent charting with existing components.
 * Follows SENTINEL dark theme design.
 */

import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Area
} from "recharts";
import { Card } from "@tremor/react";
import { Thermometer, Clock } from "lucide-react";

interface ThermalRunwayChartProps {
  data: {
    time_points: string[];
    without_precooling: number[];
    with_precooling: number[];
  };
  outagePeriod: {
    start: string;
    end: string;
  };
  metrics: {
    runwayWithout: number;
    runwayWith: number;
    comfortBreachTime: string;
    recoveryTime: string;
  };
}

// Custom tooltip component
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-gray-900 border border-gray-700 p-3 rounded shadow-lg">
        <p className="font-medium text-gray-300">{label}</p>
        <div className="space-y-1 mt-2">
          {payload.map((entry: any, idx: number) => (
            <div key={idx} className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-sm">
                {entry.name}: <span className="font-medium">{entry.value}°C</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
};

// Format chart data
function prepareChartData(
  timePoints: string[],
  withoutPrecooling: number[],
  withPrecooling: number[]
) {
  const comfortLimit = 26.0; // Comfort limit is fixed at 26°C
  return timePoints.map((time, idx) => ({
    time,
    "Without Pre-cooling": withoutPrecooling[idx],
    "With SENTINEL Pre-cooling": withPrecooling[idx],
    comfortLimit
  }));
}

// Find index of outage start and end
function findOutageIndices(timePoints: string[], outageStart: string, outageEnd: string) {
  const startIdx = timePoints.findIndex(t => t === outageStart);
  const endIdx = timePoints.findIndex(t => t === outageEnd);
  return { startIdx, endIdx };
}

export function ThermalRunwayChart({ data, outagePeriod, metrics }: ThermalRunwayChartProps) {
  const [, setHoveredPoint] = useState<number | null>(null);

  const chartData = prepareChartData(
    data.time_points,
    data.without_precooling,
    data.with_precooling
  );

  const { startIdx, endIdx } = findOutageIndices(
    data.time_points,
    outagePeriod.start,
    outagePeriod.end
  );

  // Calculate breach points
  const comfortLimit = 26.0;
  const breachWithoutIdx = data.without_precooling.findIndex(temp => temp >= comfortLimit);
  const breachWithIdx = data.with_precooling.findIndex(temp => temp >= comfortLimit);

  // Handle mouse events for hover effects
  const handleMouseMove = (e: any) => {
    if (e.activeTooltipIndex !== undefined) {
      setHoveredPoint(e.activeTooltipIndex);
    }
  };

  const handleMouseLeave = () => {
    setHoveredPoint(null);
  };

  return (
    <div className="space-y-4">
      <div className="relative h-64 min-h-[256px] w-full overflow-hidden flex">
        <ResponsiveContainer width="100%" height="100%" debounce={0}>
          <LineChart
            data={chartData}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#374151"
              horizontal={true}
              vertical={false}
            />

            <XAxis
              dataKey="time"
              stroke="#9CA3AF"
              fontSize={12}
              tickLine={false}
              axisLine={{ stroke: "#4B5563" }}
              tick={{ fill: "#9CA3AF" }}
            />

            <YAxis
              stroke="#9CA3AF"
              fontSize={12}
              tickLine={false}
              axisLine={{ stroke: "#4B5563" }}
              tick={{ fill: "#9CA3AF" }}
              domain={[20, 30]}
              label={{
                value: "Temperature (°C)",
                angle: -90,
                position: "insideLeft",
                offset: 10,
                fill: "#9CA3AF",
                fontSize: 12
              }}
            />

            <Tooltip content={<CustomTooltip />} />
            <Legend
              verticalAlign="top"
              height={36}
              iconType="circle"
              wrapperStyle={{ fontSize: "12px", color: "#9CA3AF" }}
            />

            {/* Comfort limit reference line */}
            <ReferenceLine
              y={comfortLimit}
              stroke="#EF4444"
              strokeDasharray="3 3"
              strokeWidth={1.5}
              label={{
                value: "Comfort Limit",
                position: "right",
                fill: "#EF4444",
                fontSize: 12
              }}
            />

            {/* Outage period shading */}
            {startIdx >= 0 && endIdx >= 0 && (
              <ReferenceLine
                x={data.time_points[startIdx]}
                stroke="#F59E0B"
                strokeWidth={2}
                label={{
                  value: "LOAD SHEDDING",
                  position: "insideTopLeft",
                  fill: "#F59E0B",
                  fontSize: 10,
                  offset: 5
                }}
              />
            )}

            {startIdx >= 0 && endIdx >= 0 && (
              <ReferenceLine
                x={data.time_points[endIdx]}
                stroke="#10B981"
                strokeWidth={2}
                label={{
                  value: "POWER BACK",
                  position: "insideTopRight",
                  fill: "#10B981",
                  fontSize: 10,
                  offset: 5
                }}
              />
            )}

            {/* Outage period background shading */}
            {startIdx >= 0 && endIdx >= 0 && (
              <Area
                type="monotone"
                dataKey="comfortLimit"
                stroke="none"
                fill="#F59E0B"
                fillOpacity={0.1}
                activeDot={false}
                connectNulls={true}
                data={chartData.slice(startIdx, endIdx + 1)}
              />
            )}

            {/* Without pre-cooling line (dashed) */}
            <Line
              type="monotone"
              dataKey="Without Pre-cooling"
              stroke="#9CA3AF"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={{ r: 3, strokeWidth: 2, fill: "#1F2937" }}
              activeDot={{ r: 5, strokeWidth: 2, fill: "#9CA3AF" }}
              connectNulls={true}
            />

            {/* With pre-cooling line (solid) */}
            <Line
              type="monotone"
              dataKey="With SENTINEL Pre-cooling"
              stroke="#3B82F6"
              strokeWidth={3}
              dot={{ r: 4, strokeWidth: 2, fill: "#1F2937" }}
              activeDot={{ r: 6, strokeWidth: 2, fill: "#3B82F6" }}
              connectNulls={true}
            />

            {/* Breach point markers */}
            {breachWithoutIdx >= 0 && (
              <ReferenceLine
                x={data.time_points[breachWithoutIdx]}
                stroke="#EF4444"
                strokeWidth={1}
                strokeDasharray="3 3"
                label={{
                  value: "Breach",
                  position: "top",
                  fill: "#EF4444",
                  fontSize: 10
                }}
              />
            )}

            {breachWithIdx >= 0 && (
              <ReferenceLine
                x={data.time_points[breachWithIdx]}
                stroke="#3B82F6"
                strokeWidth={1}
                strokeDasharray="3 3"
                label={{
                  value: "Breach",
                  position: "top",
                  fill: "#3B82F6",
                  fontSize: 10
                }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>

        {/* Current time indicator */}
        <div className="absolute top-0 left-0 mt-2 ml-2">
          <div className="flex items-center gap-1 bg-gray-800 px-2 py-1 rounded text-xs">
            <Clock className="h-3 w-3" />
            <span>NOW: 14:30</span>
          </div>
        </div>
      </div>

      {/* Key metrics comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="bg-gray-800/50">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-3 h-3 rounded-full bg-gray-400"></div>
            <h4 className="font-medium text-gray-300">Without Pre-cooling</h4>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-400">Thermal Runway</span>
              <span className="text-xl font-bold text-gray-300">{metrics.runwayWithout} min</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-400">Comfort Breach</span>
              <span className="font-medium text-red-400">{metrics.comfortBreachTime}</span>
            </div>
            <div className="text-xs text-gray-500 mt-2">
              Building reaches uncomfortable temperature during outage
            </div>
          </div>
        </Card>

        <Card className="bg-blue-900/30 border border-blue-700/50">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-3 h-3 rounded-full bg-blue-500"></div>
            <h4 className="font-medium text-blue-300">With SENTINEL Pre-cooling</h4>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-blue-300/80">Thermal Runway</span>
              <span className="text-xl font-bold text-blue-300">{metrics.runwayWith} min</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-blue-300/80">Comfort Maintained</span>
              <span className="font-medium text-emerald-400">✓ Yes</span>
            </div>
            <div className="text-xs text-blue-400/60 mt-2">
              Pre-cooling extends comfort through entire outage
            </div>
          </div>
        </Card>
      </div>

      {/* Improvement summary */}
      <div className="flex items-center justify-between p-3 bg-gray-800 rounded">
        <div className="flex items-center gap-3">
          <Thermometer className="h-5 w-5 text-blue-400" />
          <div>
            <div className="font-medium">+{metrics.runwayWith - metrics.runwayWithout} min extended comfort</div>
            <div className="text-sm text-gray-400">
              Pre-cooling adds {(metrics.runwayWith / metrics.runwayWithout).toFixed(1)}× more time before comfort breach
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-emerald-400">
            +{Math.round((metrics.runwayWith - metrics.runwayWithout) / metrics.runwayWithout * 100)}%
          </div>
          <div className="text-sm text-gray-400">improvement</div>
        </div>
      </div>
    </div>
  );
}
