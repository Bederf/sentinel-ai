/**
 * CrisisOverlay — 4-panel crisis alert rendered INSIDE ArcadeView div.
 * Replaces FloorStack + SummaryStrip when urgency gate fires.
 * Phase 167-03.
 *
 * NOT position:fixed — fills its parent container.
 */

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
  const isSupervised = deploymentMode === "supervised";

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

      {/* Panel 1 — VOICE */}
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
          VOICE
        </div>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "#f59e0b",
            lineHeight: 1.4,
          }}
        >
          {alertText || "Alert condition detected."}
        </div>
      </div>

      {/* Panel 2 — WHERE + TIME */}
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
          WHERE + TIME
        </div>
        <div
          style={{
            fontSize: 13,
            color: "#e2e8f0",
          }}
        >
          {affectedFloor ? (
            <>
              <span style={{ fontWeight: 600 }}>{affectedFloor}</span>
              {" · "}
              <span>{timeLabel(timeToDiscomfort)}</span>
            </>
          ) : (
            <span>{timeLabel(timeToDiscomfort)}</span>
          )}
        </div>
      </div>

      {/* Panel 3 — WHY */}
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
          WHY
        </div>
        <div
          style={{
            fontSize: 12,
            color: "#cbd5e1",
            lineHeight: 1.5,
          }}
        >
          {reasoningSummary || "No reasoning available."}
        </div>
      </div>

      {/* Panel 4 — NEXT */}
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
          NEXT
        </div>
        <div
          style={{
            fontSize: 12,
            color: "#cbd5e1",
            lineHeight: 1.5,
            marginBottom: 10,
          }}
        >
          {recommendedAction || "Monitor conditions."}
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
              APPROVE
            </button>
          )}
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
        </div>
      </div>
    </div>
  );
}
