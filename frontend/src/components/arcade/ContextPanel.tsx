/**
 * ContextPanel — slides in from right when a floor is selected in FloorStack.
 * Shows floor-scoped intelligence summary. Content depth added in Phase 168.
 * Phase 167-02.
 */

interface ContextPanelProps {
  open: boolean;
  floorId: string | null;
  floorLabel: string;
  siteId: string;
  onClose: () => void;
}

export function ContextPanel({
  open,
  floorId,
  floorLabel,
  siteId: _siteId,
  onClose,
}: ContextPanelProps) {
  return (
    <div
      data-slot="context-panel"
      style={{
        position: "absolute",
        right: open ? 0 : "-320px",
        top: 0,
        width: "300px",
        height: "100%",
        background: "var(--color-sentinel-bg-panel, #0a0a0f)",
        borderLeft: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
        transition: "right 0.25s ease",
        zIndex: 50,
        padding: "16px",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        fontFamily: "system-ui, sans-serif",
        overflowY: "auto",
      }}
      aria-hidden={!open}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
          }}
        >
          Floor Intelligence
        </span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-sentinel-text-secondary, #94a3b8)",
            cursor: "pointer",
            fontSize: 14,
            padding: "4px 8px",
            borderRadius: 4,
          }}
          aria-label="Close context panel"
        >
          ✕ Close
        </button>
      </div>

      {/* Floor label */}
      <h2
        style={{
          margin: 0,
          fontSize: 18,
          fontWeight: 700,
          color: "var(--color-sentinel-text-primary, #f1f5f9)",
        }}
      >
        {floorLabel || floorId || "—"}
      </h2>

      {/* Summary placeholder */}
      <p
        style={{
          margin: 0,
          fontSize: 13,
          color: "var(--color-sentinel-text-secondary, #94a3b8)",
        }}
      >
        Floor intelligence summary
      </p>

      {/* Content placeholder — wired in Phase 168 */}
      <div
        style={{
          fontSize: 13,
          color: "var(--color-sentinel-text-secondary, #94a3b8)",
          padding: "12px",
          borderRadius: 6,
          background: "rgba(255,255,255,0.04)",
          border: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
        }}
      >
        HVAC module loading…
      </div>
    </div>
  );
}
