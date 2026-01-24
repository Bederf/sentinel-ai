/**
 * CostBreakdownDetail Component - Detailed cost breakdown with line items
 *
 * Features:
 * - Two-column layout: failure costs vs preventive costs
 * - Line-item breakdown (parts, labor, downtime, secondary damage)
 * - Bold savings with progress bar
 * - Tremor Card, Coloured Text, ProgressBar
 *
 * Requirements:
 * - PRED-03: Detailed cost breakdown
 */

import { Card, Grid, Col, Metric, Text, Progress, Title } from "@tremor/react";

interface CostImpact {
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
}

interface CostBreakdownDetailProps {
  costImpact: CostImpact;
}

export function CostBreakdownDetail({
  costImpact,
}: CostBreakdownDetailProps) {
  // Format currency
  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  // Calculate savings percentage
  const savingsPercent = Math.round(
    (costImpact.potentialSavings / costImpact.estimatedFailureCost) * 100
  );

  return (
    <Card>
      <Grid numCols={2} className="gap-6">
        {/* Left: Failure Costs */}
        <Col>
          <Title className="text-base font-semibold text-red-600 mb-4">
            Failure Costs
          </Title>

          <div className="space-y-3">
            <div>
              <Text className="text-gray-600">Parts</Text>
              <Metric className="text-red-600 text-lg">
                {formatZAR(costImpact.failureBreakdown.parts)}
              </Metric>
              <Text className="text-xs text-gray-500">
                Emergency premium +50%
              </Text>
            </div>

            <div>
              <Text className="text-gray-600">Labour</Text>
              <Metric className="text-red-600 text-lg">
                {formatZAR(costImpact.failureBreakdown.labor)}
              </Metric>
              <Text className="text-xs text-gray-500">
                Overtime + callout
              </Text>
            </div>

            <div>
              <Text className="text-gray-600">Downtime</Text>
              <Metric className="text-red-600 text-lg">
                {formatZAR(costImpact.failureBreakdown.downtime)}
              </Metric>
              <Text className="text-xs text-gray-500">
                Mall hours, SLA penalty risk
              </Text>
            </div>

            <div>
              <Text className="text-gray-600">Secondary Damage</Text>
              <Metric className="text-red-600 text-lg">
                {formatZAR(costImpact.failureBreakdown.secondaryDamage)}
              </Metric>
              <Text className="text-xs text-gray-500">
                System stress risk
              </Text>
            </div>

            <div className="border-t border-gray-200 pt-3">
              <Text className="font-semibold text-gray-900">Total</Text>
              <Metric className="text-red-600">
                {formatZAR(costImpact.estimatedFailureCost)}
              </Metric>
            </div>
          </div>
        </Col>

        {/* Right: Preventive Costs */}
        <Col>
          <Title className="text-base font-semibold text-emerald-600 mb-4">
            Preventive Costs
          </Title>

          <div className="space-y-3">
            <div>
              <Text className="text-gray-600">Parts</Text>
              <Metric className="text-emerald-600 text-lg">
                {formatZAR(costImpact.preventiveBreakdown.parts)}
              </Metric>
              <Text className="text-xs text-gray-500">
                Planned procurement
              </Text>
            </div>

            <div>
              <Text className="text-gray-600">Labour</Text>
              <Metric className="text-emerald-600 text-lg">
                {formatZAR(costImpact.preventiveBreakdown.labor)}
              </Metric>
              <Text className="text-xs text-gray-500">
                Scheduled maintenance
              </Text>
            </div>

            <div>
              <Text className="text-gray-600">Downtime</Text>
              <Metric className="text-emerald-600 text-lg">
                {formatZAR(costImpact.preventiveBreakdown.downtime)}
              </Metric>
              <Text className="text-xs text-gray-500">
                Minor, planned window
              </Text>
            </div>

            <div className="border-t border-gray-200 pt-3">
              <Text className="font-semibold text-gray-900">Total</Text>
              <Metric className="text-emerald-600">
                {formatZAR(costImpact.estimatedPreventiveCost)}
              </Metric>
            </div>
          </div>
        </Col>
      </Grid>

      {/* Bottom: Savings */}
      <div className="border-t border-gray-200 mt-6 pt-4">
        <div className="mb-3">
          <Text className="text-sm text-gray-600">Potential Savings</Text>
          <Metric className="text-emerald-600">
            {formatZAR(costImpact.potentialSavings)}
          </Metric>
        </div>

        <Progress value={savingsPercent} color="emerald" />

        {costImpact.story && (
          <Text className="text-sm text-gray-600 mt-3 italic">
            {costImpact.story}
          </Text>
        )}
      </div>
    </Card>
  );
}
