/**
 * CrisisOverlay — 4-panel crisis alert rendered INSIDE ArcadeView div.
 * Replaces FloorStack + SummaryStrip when urgency gate fires.
 * Phase 167-03.
 *
 * NOT position:fixed — fills its parent container.
 */

import { buildDecisionSurface } from "@/lib/decisionSurface";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CrisisOverlayProps {
  alertText: string;
  reasoningSummary: string;
  recommendedAction: string;
  timeToDiscomfort: number | null; // minutes
  affectedFloor: string | null;    // e.g. "B1"
  deploymentMode: string;          // "ghost"|"advisory"|"supervised"|"autonomous"
  onDismiss: () => void;
  onApprove: () => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function timeLabel(minutes: number | null): string {
  if (minutes === null || minutes === undefined) return "Time unknown";
  return `~${minutes} min`;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function CrisisOverlay({
  alertText,
  reasoningSummary,
  recommendedAction,
  timeToDiscomfort,
  affectedFloor,
  deploymentMode,
  onDismiss,
  onApprove,
}: CrisisOverlayProps) {
  const surface = buildDecisionSurface({
    alert_text: alertText,
    reasoning_summary: reasoningSummary,
    recommended_action: recommendedAction,
    time_to_discomfort: timeToDiscomfort,
    building_metadata: {
      deployment_mode: deploymentMode as "ghost" | "advisory" | "supervised" | "autonomous",
    },
  });
  const isSupervised = surface.behavior.showApproval;
  const canDismiss = deploymentMode !== "autonomous";

  return (
    <div
      data-slot="crisis-overlay"
      style={{
        display: "flex",
        flexDirection: "column",
        borderRadius: 6,
        overflow: "hidden",
        border: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: "#dc2626",
          padding: "10px 14px",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 16 }}>⚠</span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            color: "#fff",
          }}
        >
          SENTINEL ALERT
        </span>
      </div>

      {/* Panel 1 — CAUSE */}
      <div
        style={{
          background: "var(--color-sentinel-bg-panel, #0a0a0f)",
          borderBottom: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
          padding: "10px 14px",
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
            marginBottom: 4,
          }}
        >
          CAUSE
        </div>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "#f59e0b",
            lineHeight: 1.4,
          }}
        >
          {surface.cause}
        </div>
      </div>

      {/* Panel 2 — IMPACT */}
      <div
        style={{
          background: "var(--color-sentinel-bg-panel, #0a0a0f)",
          borderBottom: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
          padding: "10px 14px",
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
            marginBottom: 4,
          }}
        >
          IMPACT
        </div>
        <div
          style={{
            fontSize: 13,
            color: "#e2e8f0",
            lineHeight: 1.5,
          }}
        >
          <div>{surface.impact}</div>
          <div style={{ color: "#94a3b8", marginTop: 6 }}>{surface.action.tradeoff}</div>
        </div>
      </div>

      {/* Panel 3 — TIME */}
      <div
        style={{
          background: "var(--color-sentinel-bg-panel, #0a0a0f)",
          borderBottom: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
          padding: "10px 14px",
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
            marginBottom: 4,
          }}
        >
          TIME
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <span style={{ fontSize: 12, color: "#94a3b8" }}>{surface.time.label}</span>
          <span style={{ fontSize: 20, fontWeight: 700, color: "#f8fafc" }}>
            {timeLabel(timeToDiscomfort)}
          </span>
          <span style={{ fontSize: 12, color: "#cbd5e1" }}>{surface.time.detail}</span>
          {affectedFloor && (
            <span style={{ fontSize: 12, color: "#94a3b8" }}>Affected floor: {affectedFloor}</span>
          )}
        </div>
      </div>

      {/* Panel 4 — ACTION */}
      <div
        style={{
          background: "var(--color-sentinel-bg-panel, #0a0a0f)",
          padding: "10px 14px",
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
            marginBottom: 6,
          }}
        >
          ACTION
        </div>
        <div
          style={{
            fontSize: 12,
            color: "#cbd5e1",
            lineHeight: 1.5,
            marginBottom: 10,
          }}
        >
          <div>{surface.action.summary}</div>
          {!surface.behavior.showResultOnly && (
            <div style={{ marginTop: 6, color: "#f8fafc", fontWeight: 600 }}>
              {surface.action.operatorPrompt}
            </div>
          )}
          <div style={{ marginTop: 6 }}>{surface.action.expectedOutcome}</div>
          {surface.behavior.showInstructions && surface.action.bmsGuide && (
            <div style={{ marginTop: 8, color: "#94a3b8" }}>
              {surface.action.bmsGuide.navigationPath.join(" -> ")}
            </div>
          )}
          {surface.behavior.showResultOnly && (
            <div style={{ marginTop: 8, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em",
              color: surface.mode === "autonomous" ? "#6ee7b7" : "#94a3b8" }}>
              {surface.mode === "autonomous"
                ? "SENTINEL executed — verifying result"
                : "Ghost mode — observe only, no write from this surface"}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {isSupervised && (
            <button
              onClick={onApprove}
              style={{
                background: "#16a34a",
                color: "#fff",
                border: "none",
                borderRadius: 4,
                padding: "6px 14px",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                letterSpacing: "0.04em",
                textTransform: "uppercase",
              }}
            >
              HOLD TO APPROVE
            </button>
          )}
          {canDismiss && (
            <button
              onClick={onDismiss}
              style={{
                background: "rgba(255,255,255,0.06)",
                color: "var(--color-sentinel-text-secondary, #94a3b8)",
                border: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
                borderRadius: 4,
                padding: "6px 14px",
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
