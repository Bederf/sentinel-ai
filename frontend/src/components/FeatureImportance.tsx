/** Feature Importance Visualization Component.

This component displays feature importance for Random Forest classifiers,
showing which features are most predictive of equipment failures.
*/


import { AlertCircle, TrendingUp } from "lucide-react";
import { classificationApi, type FeatureImportanceItem } from "@/lib/api";
import { useState, useEffect } from "react";

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
      <Card className="animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
        <div className="h-64 bg-gray-200 rounded mb-4"></div>
        <div className="h-40 bg-gray-200 rounded"></div>
      </Card>
    );
  }

  if (error) {
    return (
      <Callout
        title="Error loading feature importance"
        icon={AlertCircle}
        color="rose"
      >
        {(error as Error).message || "Unknown error"}
      </Callout>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Callout
        title="No feature importance data available"
        icon={AlertCircle}
        color="yellow"
      >
        No classifier trained for {equipmentType}
      </Callout>
    );
  }

  // Format importance as percentage
  const chartData = data.map((item: FeatureImportanceItem) => ({
    feature: formatFeatureName(item.feature),
    importance: item.importance * 100,
  }));

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <Title className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-blue-500" />
          Key Failure Indicators - {equipmentType.toUpperCase()}
        </Title>
        <Badge color="blue" size="sm">
          Top {data.length} Features
        </Badge>
      </div>

      {/* Bar Chart */}
      <div className="mb-6">
        <BarChart
          data={chartData}
          index="feature"
          categories={["importance"]}
          colors={["blue"]}
          valueFormatter={(value) => `${value.toFixed(1)}%`}
          layout="vertical"
          showAnimation={true}
          showLegend={false}
          className="h-64"
        />
      </div>

      {/* Detailed Table */}
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Rank</TableHeaderCell>
            <TableHeaderCell>Feature</TableHeaderCell>
            <TableHeaderCell>Importance</TableHeaderCell>
            <TableHeaderCell>Description</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((item: FeatureImportanceItem, index: number) => (
            <TableRow key={item.feature}>
              <TableCell>
                <Badge
                  color={index < 3 ? "blue" : "gray"}
                  size="sm"
                >
                  #{index + 1}
                </Badge>
              </TableCell>
              <TableCell className="font-medium">
                {formatFeatureName(item.feature)}
              </TableCell>
              <TableCell>
                {(item.importance * 100).toFixed(1)}%
              </TableCell>
              <TableCell className="text-gray-500">
                {getFeatureDescription(item.feature)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <p className="text-xs text-gray-500 mt-4">
        Feature importance shows which factors contribute most to failure predictions.
        Higher importance = stronger predictive power.
      </p>
    </Card>
  );
}

// Helper function to format feature names for display
function formatFeatureName(feature: string): string {
  return feature
    .replace(/_/g, " ")
    .replace(/([A-Z])/g, " $1")
    .trim()
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

// Helper function to get human-readable feature descriptions
function getFeatureDescription(feature: string): string {
  const descriptions: Record<string, string> = {
    // Common features
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

  // Check for exact match
  if (descriptions[feature]) {
    return descriptions[feature];
  }

  // Check for partial matches (e.g., "avg_temp_xxx")
  for (const [key, desc] of Object.entries(descriptions)) {
    if (feature.includes(key)) {
      return `${desc} (${feature.replace(key, "").replace(/_/g, " ")})`;
    }
  }

  // Default: return formatted feature name
  return formatFeatureName(feature);
}
