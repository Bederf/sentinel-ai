/**
 * CostCard Component - Cost comparison card showing ROI
 *
 * Features:
 * - Failure cost vs preventive cost comparison
 * - Bold savings display
 * - Tremor Card with Metric components
 *
 * Requirements:
 * - PRED-03: Cost impact analysis ("R12,500 repair vs R180,000 damage")
 */

import { Card, Metric, Text } from "@tremor/react";

interface CostImpact {
  estimatedFailureCost: number;
  estimatedPreventiveCost: number;
  potentialSavings: number;
}

interface CostCardProps {
  costImpact: CostImpact;
}

export function CostCard({ costImpact }: CostCardProps) {
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
      {/* Failure Cost */}
      <div className="mb-3">
        <Metric className="text-red-600">
          {formatZAR(costImpact.estimatedFailureCost)}
        </Metric>
        <Text className="text-gray-500">If failure occurs</Text>
      </div>

      {/* Preventive Cost */}
      <div className="mb-3">
        <Metric className="text-emerald-600">
          {formatZAR(costImpact.estimatedPreventiveCost)}
        </Metric>
        <Text className="text-gray-500">Preventive action</Text>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-200 my-3" />

      {/* Potential Savings */}
      <div>
        <Metric className="text-blue-600">
          {formatZAR(costImpact.potentialSavings)}
        </Metric>
        <Text className="text-gray-500">
          POTENTIAL SAVINGS ({savingsPercent}%)
        </Text>
      </div>
    </Card>
  );
}
