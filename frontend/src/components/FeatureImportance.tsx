import { AlertCircle, TrendingUp } from "lucide-react";
import { classificationApi, type FeatureImportanceItem } from "@/lib/api";
import { useState, useEffect } from "react";
import { Badge } from "./Badge";

interface FeatureImportanceProps {
  equipmentType: string;
}

export function FeatureImportance({ equipmentType }: FeatureImportanceProps) {
  const [data, setData] = useState<FeatureImportanceItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await classificationApi.getFeatureImportance(equipmentType, 10);
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err : new Error("Unknown error"));
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [equipmentType]);

  if (isLoading) {
    return (
      <div
        className="animate-pulse rounded-lg p-4"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div className="h-64 bg-gray-200 rounded mb-4"></div>
        <div className="h-40 bg-gray-200 rounded"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="p-3 rounded-md text-sm flex items-center gap-2"
        style={{
          background: "rgba(220,38,38,0.15)",
          border: "1px solid rgba(220,38,38,0.3)",
          color: "var(--color-sentinel-red)",
        }}
      >
        <AlertCircle className="w-4 h-4 flex-shrink-0" />
        <span className="font-medium">Error loading feature importance</span>
        <span>{(error as Error).message || "Unknown error"}</span>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div
        className="p-3 rounded-md text-sm flex items-center gap-2"
        style={{
          background: "rgba(245,158,11,0.15)",
          border: "1px solid rgba(245,158,11,0.3)",
          color: "var(--color-sentinel-amber)",
        }}
      >
        <AlertCircle className="w-4 h-4 flex-shrink-0" />
        <span className="font-medium">No feature importance data available</span>
        <span>No classifier trained for {equipmentType}</span>
      </div>
    );
  }

  const chartData = data.map((item: FeatureImportanceItem) => ({
    feature: formatFeatureName(item.feature),
    importance: item.importance * 100,
  }));

  const maxImportance = Math.max(...chartData.map(d => d.importance), 0.1);

  return (
    <div
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="flex items-center gap-2 text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          <TrendingUp className="w-5 h-5 text-blue-500" />
          Key Failure Indicators - {equipmentType.toUpperCase()}
        </h3>
        <Badge style={{ background: "rgba(59,130,246,0.15)", color: "var(--color-sentinel-blue)" }}>
          Top {data.length} Features
        </Badge>
      </div>

      <div className="mb-6 space-y-2">
        {chartData.map((item) => (
          <div key={item.feature} className="flex items-center gap-3">
            <span className="text-xs font-medium w-32 text-right truncate" style={{ color: "var(--color-sentinel-text-secondary)", flexShrink: 0 }}>
              {item.feature}
            </span>
            <div className="flex-1 h-5 rounded" style={{ background: "var(--color-sentinel-bg-secondary)", overflow: "hidden" }}>
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${(item.importance / maxImportance) * 100}%`,
                  background: "var(--color-sentinel-blue)",
                }}
              />
            </div>
            <span className="text-xs font-medium w-12 text-right" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {item.importance.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>

      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-3 py-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>Rank</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-3 py-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>Feature</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-3 py-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>Importance</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-3 py-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>Description</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item: FeatureImportanceItem, index: number) => (
            <tr key={item.feature} style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
              <td className="px-3 py-2">
                <Badge
                  style={{
                    background: index < 3 ? "rgba(59,130,246,0.15)" : "rgba(142,142,142,0.15)",
                    color: index < 3 ? "var(--color-sentinel-blue)" : "var(--color-sentinel-text-secondary)",
                  }}
                >
                  #{index + 1}
                </Badge>
              </td>
              <td className="px-3 py-2 text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {formatFeatureName(item.feature)}
              </td>
              <td className="px-3 py-2 text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {(item.importance * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-2 text-sm" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {getFeatureDescription(item.feature)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="text-xs mt-4" style={{ color: "var(--color-sentinel-text-disabled)" }}>
        Feature importance shows which factors contribute most to failure predictions.
        Higher importance = stronger predictive power.
      </p>
    </div>
  );
}

function formatFeatureName(feature: string): string {
  return feature
    .replace(/_/g, " ")
    .replace(/([A-Z])/g, " $1")
    .trim()
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function getFeatureDescription(feature: string): string {
  const descriptions: Record<string, string> = {
    "age_years": "Equipment age in years",
    "criticality_score": "Building criticality (0-1)",
    "total_work_orders": "Total maintenance work orders",
    "avg_temp": "Average temperature",
    "temp_std": "Temperature variation",
    "temp_trend": "Temperature trend over time",
    "avg_pressure": "Average pressure",
    "pressure_std": "Pressure variation",
    "kw_rating": "Power rating in kW",
    "efficiency_ratio": "Energy efficiency ratio",
    "run_hours": "Total runtime hours",
    "start_stop_count": "Number of start/stop cycles",
    "vibration": "Vibration level",
    "battery_voltage": "Battery voltage",
    "battery_age_years": "Battery age",
    "estimated_runtime_minutes": "Estimated runtime on battery",
    "filter_age_days": "Filter age in days",
    "valve_position": "Valve position (0-100%)",
    "airflow_cfm": "Airflow rate",
    "static_pressure": "Static pressure",
    "belt_age_months": "Belt age in months",
    "kva_rating": "KVA rating",
    "fuel_level_percent": "Fuel level percentage",
    "load_percent": "Current load percentage",
    "last_test_days": "Days since last test",
  };

  if (descriptions[feature]) {
    return descriptions[feature];
  }

  for (const [key, desc] of Object.entries(descriptions)) {
    if (feature.includes(key)) {
      return `${desc} (${feature.replace(key, "").replace(/_/g, " ")})`;
    }
  }

  return formatFeatureName(feature);
}
