/**
 * ContextPanel — slides in from right when a floor is selected in FloorStack.
 * Shows floor label + outcome of POST /api/decisions/trigger (module_display).
 * The same module_display is applied to the overview below via onModuleDisplayChange.
 */

interface FloorIncidentInfo {
  affected?: boolean;
}

interface ContextPanelProps {
  open: boolean;
  floorId: string | null;
  floorLabel: string;
  siteId: string;
  /** From POST /api/decisions/trigger — which intelligence sections to emphasize */
  moduleDisplay: Record<string, string>;
  triggerLoading: boolean;
  triggerFailed: boolean;
  /** From GET /api/decisions/current payload — crisis highlight for this floor */
  floorIncident: FloorIncidentInfo | null;
  onClose: () => void;
}

const MODULE_ORDER = [
  "hvac",
  "energy",
  "lighting",
  "solar",
  "occupancy",
  "fire",
  "security",
  "water",
] as const;

const MODULE_LABELS: Record<string, string> = {
  hvac: "HVAC",
  energy: "Energy",
  lighting: "Lighting",
  solar: "Solar & BESS",
  occupancy: "Occupancy",
  fire: "Fire safety",
  security: "Security",
  water: "Water",
};

function visibleModules(display: Record<string, string>): { key: string; mode: string }[] {
  return MODULE_ORDER.filter((k) => (display[k] ?? "hidden") !== "hidden").map((k) => ({
    key: k,
    mode: display[k] ?? "hidden",
  }));
}

export function ContextPanel({
  open,
  floorId,
  floorLabel,
  siteId: _siteId,
  moduleDisplay,
  triggerLoading,
  triggerFailed,
  floorIncident,
  onClose,
}: ContextPanelProps) {
  const visible = visibleModules(moduleDisplay);
  const showIncident =
    floorIncident?.affected === true;

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
            color: "var(--color-sentinel-text-secondary)",
          }}
        >
          Floor Intelligence
        </span>
        <button
          onClick={onClose}
          type="button"
          style={{
            background: "none",
            border: "none",
            color: "var(--color-sentinel-text-secondary)",
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

      <h2
        style={{
          margin: 0,
          fontSize: 18,
          fontWeight: 700,
          color: "var(--color-sentinel-text-primary)",
        }}
      >
        {floorLabel || floorId || "—"}
      </h2>

      {triggerLoading && (
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: "var(--color-sentinel-text-secondary)",
          }}
        >
          Applying floor context…
        </p>
      )}

      {!triggerLoading && triggerFailed && (
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: "var(--color-sentinel-amber)",
          }}
        >
          Could not load floor context from the server. Scroll the overview and try again, or check your connection.
        </p>
      )}

      {!triggerLoading && !triggerFailed && (
        <>
          <p
            style={{
              margin: 0,
              fontSize: 13,
              lineHeight: 1.45,
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            Selecting a floor opens the matching intelligence sections on this page (below the spatial view). This
            panel lists what the decision engine surfaced for{" "}
            <span style={{ color: "var(--color-sentinel-text-primary, #f1f5f9)" }}>
              {floorLabel || floorId}
            </span>
            .
          </p>

          {showIncident && (
            <div
              style={{
                fontSize: 12,
                padding: "10px 12px",
                borderRadius: 6,
                background: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.35)",
                color: "var(--color-sentinel-red)",
              }}
            >
              This floor is marked <strong>affected</strong> in the current incident map (crisis view).
            </div>
          )}

          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            Modules highlighted
          </div>

          {visible.length === 0 ? (
            <p style={{ margin: 0, fontSize: 13, color: "var(--color-sentinel-text-secondary, #94a3b8)" }}>
              No modules are set to show for this trigger yet.
            </p>
          ) : (
            <ul
              style={{
                margin: 0,
                paddingLeft: 18,
                fontSize: 13,
                color: "var(--color-sentinel-text-primary)",
                lineHeight: 1.6,
              }}
            >
              {visible.map(({ key, mode }) => (
                <li key={key}>
                  <span>{MODULE_LABELS[key] ?? key}</span>
                  <span style={{ color: "var(--color-sentinel-text-secondary, #94a3b8)" }}>
                    {" "}
                    — {mode === "detailed" ? "detailed" : "summary"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
