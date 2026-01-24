/**
 * PredictionCard Component - Compact card for failure predictions
 *
 * Features:
 * - Probability circle (percentage)
 * - Asset info (name, site, type)
 * - Confidence badge (high/medium/low)
 * - Timeframe (e.g., "in 21 days")
 * - Severity color coding
 * - Clickable to show full details
 *
 * Requirements:
 * - PRED-01: Display failure probability with timeframe
 * - PRED-02: Explainability preview (confidence, severity)
 */

import { Card, Badge, Text, Title, Flex, Metric, Callout } from "@tremor/react";
import {
  AlertTriangle,
  Clock,
  Activity,
  TrendingUp,
  Wrench,
} from "lucide-react";

interface PredictionCardProps {
  prediction: {
    id: string;
    equipment_name: string;
    site_name: string;
    equipment_type: string;
    prediction_type: string;
    probability_percent: number;
    confidence: "high" | "medium" | "low";
    predicted_failure_date: string;
    timeframe_days: number;
    severity: "critical" | "high" | "medium" | "low";
    evidence: {
      repeat_work_orders: number;
      asset_age_years: number;
    };
  };
  onClick?: () => void;
}

export function PredictionCard({ prediction, onClick }: PredictionCardProps) {
  // Severity color mapping
  const severityColors = {
    critical: "red",
    high: "orange",
    medium: "yellow",
    low: "blue",
  } as const;

  const severityColor = severityColors[prediction.severity];

  // Confidence color
  const confidenceColors = {
    high: "emerald",
    medium: "yellow",
    low: "gray",
  } as const;

  const confidenceColor = confidenceColors[prediction.confidence];

  // Format date
  const failureDate = new Date(prediction.predicted_failure_date);
  const formattedDate = failureDate.toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
  });

  return (
    <Card
      className="cursor-pointer hover:shadow-lg transition-shadow duration-200"
      onClick={onClick}
    >
      {/* Header: Probability Circle + Severity Badge */}
      <Flex justifyContent="between" alignItems="start" className="mb-3">
        <div className="flex items-center gap-3">
          {/* Probability Circle */}
          <div className="relative w-16 h-16">
            <svg className="w-full h-full transform -rotate-90">
              {/* Background circle */}
              <circle
                cx="32"
                cy="32"
                r="28"
                fill="none"
                className="stroke-gray-200"
                strokeWidth="6"
              />
              {/* Progress circle */}
              <circle
                cx="32"
                cy="32"
                r="28"
                fill="none"
                className={`stroke-${severityColor === "red" ? "red" : severityColor === "orange" ? "orange" : "yellow"}-500`}
                strokeWidth="6"
                strokeDasharray={`${(prediction.probability_percent / 100) * 176} 176`}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-sm font-bold text-gray-900">
                {prediction.probability_percent}%
              </span>
            </div>
          </div>

          <div>
            <Text className="text-xs text-gray-500">Failure Probability</Text>
            <Text className="text-sm font-semibold text-gray-900">
              in {prediction.timeframe_days} days
            </Text>
          </div>
        </div>

        {/* Severity Badge */}
        <Badge color={severityColor} size="sm">
          {prediction.severity.toUpperCase()}
        </Badge>
      </Flex>

      {/* Equipment Info */}
      <div className="mb-3">
        <Title className="text-lg font-semibold text-gray-900 mb-1">
          {prediction.equipment_name}
        </Title>
        <Flex alignItems="center" className="gap-2">
          <Activity className="w-3 h-3 text-gray-500" />
          <Text className="text-sm text-gray-600">
            {prediction.site_name} • {prediction.equipment_type}
          </Text>
        </Flex>
      </div>

      {/* Prediction Type */}
      <Callout
        title={formatPredictionType(prediction.prediction_type)}
        icon={AlertTriangle}
        color={severityColor}
        className="mb-3"
      >
        Predicted failure: {formattedDate}
      </Callout>

      {/* Evidence Preview */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        {/* Repeat Work Orders */}
        <div className="flex items-center gap-2">
          <Wrench className="w-3 h-3 text-gray-500" />
          <div>
            <Text className="text-xs text-gray-500">Repeat Calls</Text>
            <Text className="text-sm font-semibold text-gray-900">
              {prediction.evidence.repeat_work_orders}
            </Text>
          </div>
        </div>

        {/* Asset Age */}
        <div className="flex items-center gap-2">
          <Clock className="w-3 h-3 text-gray-500" />
          <div>
            <Text className="text-xs text-gray-500">Asset Age</Text>
            <Text className="text-sm font-semibold text-gray-900">
              {prediction.evidence.asset_age_years} years
            </Text>
          </div>
        </div>
      </div>

      {/* Confidence Badge */}
      <Flex justifyContent="end" className="gap-2">
        <Badge color={confidenceColor} size="xs">
          {prediction.confidence.toUpperCase()} CONFIDENCE
        </Badge>
      </Flex>
    </Card>
  );
}

/**
 * Format prediction type for display
 */
function formatPredictionType(type: string): string {
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
