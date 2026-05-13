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
    <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
      {/* Failure Cost */}
      <div className="mb-3">
        <div className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-red)' }}>
          {formatZAR(costImpact.estimatedFailureCost)}
        </div>
        <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>If failure occurs</span>
      </div>

      {/* Preventive Cost */}
      <div className="mb-3">
        <div className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-green)' }}>
          {formatZAR(costImpact.estimatedPreventiveCost)}
        </div>
        <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Preventive action</span>
      </div>

      {/* Divider */}
      <div className="border-t my-3" style={{ borderColor: 'var(--color-sentinel-border)' }} />

      {/* Potential Savings */}
      <div>
        <div className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-blue)' }}>
          {formatZAR(costImpact.potentialSavings)}
        </div>
        <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          POTENTIAL SAVINGS ({savingsPercent}%)
        </span>
      </div>
    </div>
  );
}
