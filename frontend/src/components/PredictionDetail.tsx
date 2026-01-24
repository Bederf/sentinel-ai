/**
 * PredictionDetail Component - Full-screen modal for prediction details
 *
 * Features:
 * - Complete prediction evidence
 * - Contributing factors with weights
 * - Related work orders
 * - Similar historical failures
 * - Technician notes
 * - Financial impact analysis
 * - Cost impact analysis (NEW)
 * - Recommended actions
 *
 * Requirements:
 * - PRED-02: Full explainability with evidence breakdown
 * - PRED-03: Cost impact analysis with breakdowns
 */

import { useState } from "react";
import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Divider,
  Badge,
  Text,
  Title,
  Flex,
  Card,
  Grid,
  Col,
  Callout,
  List,
  ListItem,
  Metric,
  Progress,
  Button,
} from "@tremor/react";
import {
  X,
  AlertTriangle,
  TrendingUp,
  Wrench,
  Clock,
  DollarSign,
  FileText,
  Activity,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { CostCard } from "./CostCard";
import { CostBreakdownDetail } from "./CostBreakdownDetail";

interface PredictionDetailProps {
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
      repeat_period_months: number;
      alarm_frequency: Record<string, number>;
      asset_age_years: number;
      expected_life_years: number;
      technician_notes: string[];
      latest_reading: {
        parameter: string;
        value: number;
        baseline: number;
        threshold: number;
        trend: string;
      };
    };
    contributing_factors: Array<{
      factor: string;
      weight: number;
      description: string;
    }>;
    similar_failures: Array<{
      site: string;
      equipment: string;
      failure_date: string;
      common_factors: string[];
    }>;
    financial_impact: {
      repair_cost_zar: number;
      replacement_cost_zar: number;
      downtime_cost_per_hour_zar: number;
      estimated_repair_hours: number;
      potential_loss_zar: number;
    };
    costImpact?: {
      estimatedFailureCost: number;
      estimatedPreventiveCost: number;
      potentialSavings: number;
      failureBreakdown: {
        parts: number;
        labor: number;
        downtime: number;
        secondaryDamage: number;
      };
      preventiveBreakdown: {
        parts: number;
        labor: number;
        downtime: number;
      };
      story?: string;
    };
    recommended_action: string;
    parts_required: string[];
    urgency: string;
  };
  isOpen: boolean;
  onClose: () => void;
}

export function PredictionDetail({
  prediction,
  isOpen,
  onClose,
}: PredictionDetailProps) {
  const [showCostBreakdown, setShowCostBreakdown] = useState(false);

  if (!isOpen) return null;

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

  // Format currency
  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  // Calculate trend percentage
  const trendPercent = Math.round(
    ((prediction.evidence.latest_reading.value - prediction.evidence.latest_reading.baseline) /
      prediction.evidence.latest_reading.baseline) *
      100
  );

  return (
    <Dialog open={isOpen} onClose={onClose} className="z-50">
      <DialogPanel className="max-w-5xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <Flex justifyContent="between" alignItems="start" className="mb-4">
          <div>
            <DialogTitle className="text-2xl font-bold text-gray-900 mb-2">
              Failure Prediction Details
            </DialogTitle>
            <Flex className="gap-2">
              <Badge color={severityColor} size="sm">
                {prediction.severity.toUpperCase()}
              </Badge>
              <Badge color={confidenceColor} size="sm">
                {prediction.confidence.toUpperCase()} CONFIDENCE
              </Badge>
              <Badge color="gray" size="sm">
                {prediction.equipment_type.toUpperCase()}
              </Badge>
            </Flex>
          </div>
          <Button
            variant="light"
            icon={X}
            onClick={onClose}
            className="tremor-Button-root"
          />
        </Flex>

        <Divider />

        {/* Probability & Timeframe */}
        <Grid numCols={3} className="gap-4 mt-4 mb-6">
          <Col>
            <Card>
              <Metric>{prediction.probability_percent}%</Metric>
              <Text className="text-gray-500">Failure Probability</Text>
            </Card>
          </Col>
          <Col>
            <Card>
              <Metric>{prediction.timeframe_days}</Metric>
              <Text className="text-gray-500">Days Until Failure</Text>
            </Card>
          </Col>
          <Col>
            <Card>
              <Metric>{prediction.evidence.asset_age_years} years</Metric>
              <Text className="text-gray-500">Asset Age</Text>
            </Card>
          </Col>
        </Grid>

        {/* Equipment Info */}
        <Card className="mb-6">
          <Flex justifyContent="between" className="mb-3">
            <div>
              <Title className="text-xl font-semibold text-gray-900 mb-1">
                {prediction.equipment_name}
              </Title>
              <Flex alignItems="center" className="gap-2">
                <Activity className="w-4 h-4 text-gray-500" />
                <Text className="text-gray-600">
                  {prediction.site_name} • {prediction.equipment_type}
                </Text>
              </Flex>
            </div>
          </Flex>

          <Callout
            title={formatPredictionType(prediction.prediction_type)}
            icon={AlertTriangle}
            color={severityColor}
            className="mb-3"
          >
            Predicted failure:{" "}
            {new Date(prediction.predicted_failure_date).toLocaleDateString(
              "en-ZA",
              { day: "numeric", month: "long", year: "numeric" }
            )}
          </Callout>

          <Flex className="gap-4">
            <Badge color="orange" icon={Wrench} size="sm">
              {prediction.evidence.repeat_work_orders} work orders in{" "}
              {prediction.evidence.repeat_period_months} months
            </Badge>
            <Badge color="blue" icon={Clock} size="sm">
              Expected life: {prediction.evidence.expected_life_years} years
            </Badge>
          </Flex>
        </Card>

        {/* Contributing Factors */}
        <Title className="text-lg font-semibold text-gray-900 mb-3">
          Contributing Factors
        </Title>
        <Card className="mb-6">
          <List>
            {prediction.contributing_factors.map((factor, index) => (
              <ListItem key={index}>
                <div className="w-full">
                  <Flex justifyContent="between" className="mb-2">
                    <Text className="font-semibold text-gray-900">
                      {factor.factor}
                    </Text>
                    <Text className="text-sm text-gray-600">
                      {Math.round(factor.weight * 100)}%
                    </Text>
                  </Flex>
                  <Progress value={factor.weight * 100} color={severityColor} />
                  <Text className="text-sm text-gray-600 mt-2">
                    {factor.description}
                  </Text>
                </div>
              </ListItem>
            ))}
          </List>
        </Card>

        {/* Cost Impact Analysis */}
        {prediction.costImpact && (
          <>
            <Title className="text-lg font-semibold text-gray-900 mb-3">
              Cost Impact Analysis
            </Title>

            {!showCostBreakdown ? (
              <Card className="mb-6">
                <CostCard costImpact={prediction.costImpact} />
                <Button
                  variant="light"
                  size="sm"
                  icon={ChevronDown}
                  className="mt-3"
                  onClick={() => setShowCostBreakdown(true)}
                >
                  View detailed breakdown
                </Button>
              </Card>
            ) : (
              <Card className="mb-6">
                <CostBreakdownDetail costImpact={prediction.costImpact} />
                <Button
                  variant="light"
                  size="sm"
                  icon={ChevronUp}
                  className="mt-3"
                  onClick={() => setShowCostBreakdown(false)}
                >
                  Hide breakdown
                </Button>
              </Card>
            )}
          </>
        )}

        {/* Evidence Details */}
        <Grid numCols={2} className="gap-4 mb-6">
          {/* Latest Reading */}
          <Col>
            <Title className="text-lg font-semibold text-gray-900 mb-3">
              Latest Reading
            </Title>
            <Card>
              <Flex justifyContent="between" className="mb-3">
                <Text className="text-gray-600">
                  {prediction.evidence.latest_reading.parameter.replace(/_/g, " ")}
                </Text>
                <Badge
                  color={
                    prediction.evidence.latest_reading.trend === "increasing"
                      ? "red"
                      : "blue"
                  }
                  icon={
                    prediction.evidence.latest_reading.trend === "increasing"
                      ? TrendingUp
                      : Activity
                  }
                  size="xs"
                >
                  {prediction.evidence.latest_reading.trend}
                </Badge>
              </Flex>
              <Metric>
                {prediction.evidence.latest_reading.value}
                <Text className="text-sm text-gray-500 ml-2">
                  (baseline: {prediction.evidence.latest_reading.baseline})
                </Text>
              </Metric>
              <Flex className="gap-2 mt-3">
                <div className="flex-1">
                  <Text className="text-xs text-gray-500">Change</Text>
                  <Text
                    className={`text-sm font-semibold ${
                      trendPercent > 0 ? "text-red-600" : "text-emerald-600"
                    }`}
                  >
                    {trendPercent > 0 ? "+" : ""}
                    {trendPercent}%
                  </Text>
                </div>
                <div className="flex-1">
                  <Text className="text-xs text-gray-500">Threshold</Text>
                  <Text className="text-sm font-semibold text-gray-900">
                    {prediction.evidence.latest_reading.threshold}
                  </Text>
                </div>
              </Flex>
            </Card>
          </Col>

          {/* Alarm Frequency */}
          <Col>
            <Title className="text-lg font-semibold text-gray-900 mb-3">
              Alarm Frequency (30 days)
            </Title>
            <Card>
              <List>
                {Object.entries(prediction.evidence.alarm_frequency).map(
                  ([alarm, count]) => (
                    <ListItem key={alarm}>
                      <Flex justifyContent="between" className="w-full">
                        <Text className="text-gray-600">
                          {alarm.replace(/_/g, " ")}
                        </Text>
                        <Badge color="red" size="sm">
                          {count}
                        </Badge>
                      </Flex>
                    </ListItem>
                  )
                )}
              </List>
            </Card>
          </Col>
        </Grid>

        {/* Technician Notes */}
        <Title className="text-lg font-semibold text-gray-900 mb-3">
          Technician Notes
        </Title>
        <Card className="mb-6">
          <List>
            {prediction.evidence.technician_notes.map((note, index) => (
              <ListItem key={index}>
                <Flex className="gap-3 w-full">
                  <FileText className="w-4 h-4 text-gray-500 mt-1" />
                  <div className="flex-1">
                    <Text className="text-xs text-gray-500 mb-1">
                      {note.split(":")[0]}
                    </Text>
                    <Text className="text-sm text-gray-900">
                      {note.split(":").slice(1).join(":")}
                    </Text>
                  </div>
                </Flex>
              </ListItem>
            ))}
          </List>
        </Card>

        {/* Cross-Site Pattern Recognition */}
        {prediction.similar_failures.length >= 2 && (
          <>
            <Title className="text-lg font-semibold text-gray-900 mb-3">
              🔍 Cross-Site Pattern Detected
            </Title>
            <Card className="mb-6">
              <Text className="text-gray-700 mb-3">
                This vibration pattern matches failures at{" "}
                {prediction.similar_failures.length} other sites:
              </Text>
              <List className="mb-3">
                {prediction.similar_failures.map((failure, index) => (
                  <ListItem key={index}>
                    <Flex justifyContent="between" className="w-full">
                      <Text className="font-semibold text-gray-900">
                        {failure.site} {failure.equipment}
                      </Text>
                      <Badge color="red" size="sm">
                        failed
                      </Badge>
                    </Flex>
                  </ListItem>
                ))}
              </List>
              <Callout
                title="Pattern Recognition Insight"
                icon={TrendingUp}
                color="blue"
              >
                "{prediction.site_name},{" "}
                {prediction.similar_failures
                  .slice(0, 2)
                  .map((f) => f.site)
                  .join(", ")}
                {prediction.similar_failures.length > 2 && "..."} all showing this
                early warning pattern."
              </Callout>
            </Card>
          </>
        )}

        {/* Similar Failures */}
        {prediction.similar_failures.length > 0 && (
          <>
            <Title className="text-lg font-semibold text-gray-900 mb-3">
              Similar Historical Failures
            </Title>
            <Card className="mb-6">
              <List>
                {prediction.similar_failures.map((failure, index) => (
                  <ListItem key={index}>
                    <div className="w-full">
                      <Flex justifyContent="between" className="mb-2">
                        <Text className="font-semibold text-gray-900">
                          {failure.site} - {failure.equipment}
                        </Text>
                        <XCircle className="w-4 h-4 text-red-500" />
                      </Flex>
                      <Text className="text-sm text-gray-600 mb-2">
                        Failed:{" "}
                        {new Date(failure.failure_date).toLocaleDateString(
                          "en-ZA",
                          { day: "numeric", month: "short", year: "numeric" }
                        )}
                      </Text>
                      <Flex className="gap-1 flex-wrap">
                        {failure.common_factors.map((factor, i) => (
                          <Badge key={i} color="gray" size="xs">
                            {factor}
                          </Badge>
                        ))}
                      </Flex>
                    </div>
                  </ListItem>
                ))}
              </List>
            </Card>
          </>
        )}

        {/* Financial Impact */}
        <Title className="text-lg font-semibold text-gray-900 mb-3">
          Financial Impact Analysis
        </Title>
        <Card className="mb-6">
          <Grid numCols={2} className="gap-4">
            <Col>
              <Metric>{formatZAR(prediction.financial_impact.repair_cost_zar)}</Metric>
              <Text className="text-gray-500">Repair Cost</Text>
            </Col>
            <Col>
              <Metric>
                {formatZAR(prediction.financial_impact.potential_loss_zar)}
              </Metric>
              <Text className="text-gray-500">Potential Loss</Text>
            </Col>
            <Col>
              <Metric>
                {formatZAR(
                  prediction.financial_impact.potential_loss_zar -
                    prediction.financial_impact.repair_cost_zar
                )}
              </Metric>
              <Text className="text-gray-500">Potential Savings</Text>
            </Col>
            <Col>
              <Metric>{prediction.financial_impact.estimated_repair_hours}h</Metric>
              <Text className="text-gray-500">Estimated Downtime</Text>
            </Col>
          </Grid>
        </Card>

        {/* Recommended Action */}
        <Title className="text-lg font-semibold text-gray-900 mb-3">
          Recommended Action
        </Title>
        <Callout
          title={prediction.urgency.toUpperCase()}
          icon={CheckCircle2}
          color={severityColor}
          className="mb-4"
        >
          {prediction.recommended_action}
        </Callout>

        {/* Parts Required */}
        <Card>
          <Title className="text-base font-semibold text-gray-900 mb-3">
            Parts Required
          </Title>
          <List>
            {prediction.parts_required.map((part, index) => (
              <ListItem key={index}>
                <Flex className="gap-2">
                  <Wrench className="w-4 h-4 text-gray-500" />
                  <Text className="text-gray-900">{part}</Text>
                </Flex>
              </ListItem>
            ))}
          </List>
        </Card>

        {/* Footer */}
        <Flex justifyContent="end" className="mt-6 gap-2">
          <Button variant="light" onClick={onClose}>
            Close
          </Button>
          <Button color={severityColor} icon={Wrench}>
            Schedule Maintenance
          </Button>
        </Flex>
      </DialogPanel>
    </Dialog>
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
