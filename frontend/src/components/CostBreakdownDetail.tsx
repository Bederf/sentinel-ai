/**
 * CostBreakdownDetail Component - Grafana-styled cost breakdown
 *
 * Features:
 * - Two-column layout: failure costs vs preventive costs
 * - Line-item breakdown (parts, labor, downtime, secondary damage)
 * - Bold savings with progress indicator
 * - Dark theme styling
 */

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

export function CostBreakdownDetail({ costImpact }: CostBreakdownDetailProps) {
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
    <div
      className="rounded p-4"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left: Failure Costs */}
        <div>
          <h3
            className="text-base font-semibold mb-4"
            style={{ color: "var(--color-status-error)" }}
          >
            Failure Costs
          </h3>

          <div className="space-y-4">
            <CostLineItem
              label="Parts"
              value={formatZAR(costImpact.failureBreakdown.parts)}
              description="Emergency premium +50%"
              color="var(--color-status-error)"
            />
            <CostLineItem
              label="Labour"
              value={formatZAR(costImpact.failureBreakdown.labor)}
              description="Overtime + callout"
              color="var(--color-status-error)"
            />
            <CostLineItem
              label="Downtime"
              value={formatZAR(costImpact.failureBreakdown.downtime)}
              description="Mall hours, SLA penalty risk"
              color="var(--color-status-error)"
            />
            <CostLineItem
              label="Secondary Damage"
              value={formatZAR(costImpact.failureBreakdown.secondaryDamage)}
              description="System stress risk"
              color="var(--color-status-error)"
            />

            <div
              className="pt-4"
              style={{ borderTop: "1px solid var(--color-grafana-border)" }}
            >
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                Total
              </span>
              <div
                className="text-2xl font-bold"
                style={{ color: "var(--color-status-error)" }}
              >
                {formatZAR(costImpact.estimatedFailureCost)}
              </div>
            </div>
          </div>
        </div>

        {/* Right: Preventive Costs */}
        <div>
          <h3
            className="text-base font-semibold mb-4"
            style={{ color: "var(--color-status-success)" }}
          >
            Preventive Costs
          </h3>

          <div className="space-y-4">
            <CostLineItem
              label="Parts"
              value={formatZAR(costImpact.preventiveBreakdown.parts)}
              description="Planned procurement"
              color="var(--color-status-success)"
            />
            <CostLineItem
              label="Labour"
              value={formatZAR(costImpact.preventiveBreakdown.labor)}
              description="Scheduled maintenance"
              color="var(--color-status-success)"
            />
            <CostLineItem
              label="Downtime"
              value={formatZAR(costImpact.preventiveBreakdown.downtime)}
              description="Minor, planned window"
              color="var(--color-status-success)"
            />

            <div
              className="pt-4"
              style={{ borderTop: "1px solid var(--color-grafana-border)" }}
            >
              <span
                className="text-sm font-medium"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                Total
              </span>
              <div
                className="text-2xl font-bold"
                style={{ color: "var(--color-status-success)" }}
              >
                {formatZAR(costImpact.estimatedPreventiveCost)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom: Savings */}
      <div
        className="mt-6 pt-4"
        style={{ borderTop: "1px solid var(--color-grafana-border)" }}
      >
        <div className="mb-3">
          <span
            className="text-sm"
            style={{ color: "var(--color-grafana-text-secondary)" }}
          >
            Potential Savings
          </span>
          <div
            className="text-3xl font-bold"
            style={{ color: "var(--color-status-success)" }}
          >
            {formatZAR(costImpact.potentialSavings)}
          </div>
        </div>

        {/* Progress bar */}
        <div
          className="h-2 rounded-full overflow-hidden"
          style={{ background: "var(--color-grafana-border)" }}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${savingsPercent}%`,
              background: "var(--color-status-success)",
            }}
          />
        </div>
        <span
          className="text-xs mt-1 block"
          style={{ color: "var(--color-grafana-text-disabled)" }}
        >
          {savingsPercent}% savings by taking preventive action
        </span>

        {costImpact.story && (
          <p
            className="text-sm mt-3 italic"
            style={{ color: "var(--color-grafana-text-secondary)" }}
          >
            {costImpact.story}
          </p>
        )}
      </div>
    </div>
  );
}

// Helper component for cost line items
function CostLineItem({
  label,
  value,
  description,
  color,
}: {
  label: string;
  value: string;
  description: string;
  color: string;
}) {
  return (
    <div>
      <span
        className="text-sm"
        style={{ color: "var(--color-grafana-text-secondary)" }}
      >
        {label}
      </span>
      <div className="text-lg font-semibold" style={{ color }}>
        {value}
      </div>
      <span
        className="text-xs"
        style={{ color: "var(--color-grafana-text-disabled)" }}
      >
        {description}
      </span>
    </div>
  );
}

export default CostBreakdownDetail;
