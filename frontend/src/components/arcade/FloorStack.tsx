/**
 * FloorStack — SVG floor-by-floor building visualiser.
 * Renders one rect per floor, coloured by renderer_hint and active_incident_map.
 * Phase 166-02: ArcadeView spatial interface.
 */

const FLOOR_HEIGHT = 40;
const FLOOR_GAP = 4;
const LABEL_WIDTH = 40;
const RECT_RADIUS = 4;

interface IncidentFloor {
  stack_index: number;
  svg_y_pct: number;
  affected: boolean;
}

export interface FloorStackProps {
  floorStackOrder: string[];
  floorLabels: Record<string, string>;
  activeIncidentMap: Record<string, IncidentFloor>;
  rendererHint: "quiet" | "crisis";
  onFloorClick?: (floorId: string) => void;
  selectedFloor?: string | null;
}

export function FloorStack({
  floorStackOrder,
  floorLabels,
  activeIncidentMap,
  rendererHint,
  onFloorClick,
  selectedFloor,
}: FloorStackProps) {
  if (!floorStackOrder || floorStackOrder.length === 0) {
    const fallbackH = FLOOR_HEIGHT;
    return (
      <svg
        width="100%"
        height={fallbackH}
        style={{ display: "block" }}
        aria-label="No floor data"
      >
        <rect
          x={LABEL_WIDTH + 8}
          y={0}
          width={`calc(100% - ${LABEL_WIDTH + 8}px)`}
          height={fallbackH}
          rx={RECT_RADIUS}
          fill="#374151"
        />
        <text
          x={LABEL_WIDTH + 16}
          y={fallbackH / 2 + 5}
          fill="#6b7280"
          fontSize={12}
          fontFamily="system-ui, sans-serif"
        >
          No floor data
        </text>
      </svg>
    );
  }

  const totalH =
    floorStackOrder.length * FLOOR_HEIGHT +
    (floorStackOrder.length - 1) * FLOOR_GAP;

  return (
    <svg
      width="100%"
      height={totalH}
      style={{ display: "block", overflow: "visible" }}
      aria-label="Building floor stack"
    >
      {floorStackOrder.map((floorId, idx) => {
        const y = idx * (FLOOR_HEIGHT + FLOOR_GAP);
        const incident = activeIncidentMap[floorId];
        const isAffected = rendererHint === "crisis" && incident?.affected === true;

        const fillColor = isAffected
          ? "#dc2626"
          : rendererHint === "crisis"
          ? "#0f172a"
          : "#1e3a5f";

        const label = floorLabels[floorId] ?? floorId;
        const animId = `pulse-${floorId}`;

        return (
          <g key={floorId}>
            {/* Floor label */}
            <text
              x={0}
              y={y + FLOOR_HEIGHT / 2 + 5}
              fill="var(--color-sentinel-text-secondary, #94a3b8)"
              fontSize={11}
              fontFamily="system-ui, sans-serif"
              textAnchor="start"
            >
              {label}
            </text>

            {/* Floor rect */}
            <rect
              x={LABEL_WIDTH + 8}
              y={y}
              width={`calc(100% - ${LABEL_WIDTH + 8}px)`}
              height={FLOOR_HEIGHT}
              rx={RECT_RADIUS}
              fill={fillColor}
              onClick={() => onFloorClick?.(floorId)}
              style={{ cursor: onFloorClick ? "pointer" : undefined }}
              strokeWidth={selectedFloor === floorId ? 2 : 0}
              stroke="#4a9eff"
            >
              {isAffected && (
                <animate
                  id={animId}
                  attributeName="opacity"
                  values="1;0.4;1"
                  dur="1.4s"
                  repeatCount="indefinite"
                />
              )}
            </rect>
          </g>
        );
      })}
    </svg>
  );
}
