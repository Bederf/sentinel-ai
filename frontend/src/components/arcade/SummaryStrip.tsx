/**
 * SummaryStrip — three stat pills summarising the building state.
 * Reads from DecisionMomentPayload.building_metadata.
 * Null-safe: shows dashes when data is not yet available.
 * Phase 166-02: ArcadeView spatial interface.
 */

export interface SummaryStripProps {
  equipmentCount: number | null;
  activeRiskCount: number | null;
  healthPct: number | null;
}

function healthColor(pct: number | null): string {
  if (pct === null) return "var(--color-sentinel-text-secondary, #94a3b8)";
  if (pct >= 80) return "#22c55e"; // green
  if (pct >= 50) return "#f59e0b"; // amber
  return "#ef4444"; // red
}

interface PillProps {
  label: string;
  value: string;
  valueColor?: string;
}

function StatPill({ label, value, valueColor }: PillProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "8px 16px",
        borderRadius: 8,
        background: "rgba(255,255,255,0.04)",
        border: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
        minWidth: 100,
        gap: 2,
      }}
    >
      <span
        style={{
          fontSize: 20,
          fontWeight: 700,
          fontFamily: "system-ui, sans-serif",
          color: valueColor ?? "var(--color-sentinel-text-primary, #f1f5f9)",
          lineHeight: 1.2,
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: 11,
          color: "var(--color-sentinel-text-secondary, #94a3b8)",
          fontFamily: "system-ui, sans-serif",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </span>
    </div>
  );
}

export function SummaryStrip({
  equipmentCount,
  activeRiskCount,
  healthPct,
}: SummaryStripProps) {
  const assetsValue = equipmentCount !== null ? String(equipmentCount) : "—";
  const risksValue = activeRiskCount !== null ? String(activeRiskCount) : "—";
  const healthValue = healthPct !== null ? `${Math.round(healthPct)}%` : "—%";

  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        marginBottom: 16,
        flexWrap: "wrap",
      }}
      aria-label="Building summary"
    >
      <StatPill label="Assets" value={assetsValue} />
      <StatPill
        label="Risks"
        value={risksValue}
        valueColor={
          activeRiskCount !== null && activeRiskCount > 0
            ? "#ef4444"
            : undefined
        }
      />
      <StatPill
        label="Health"
        value={healthValue}
        valueColor={healthColor(healthPct)}
      />
    </div>
  );
}
