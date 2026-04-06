/**
 * SpaceOptimizationPage — Focus room management.
 *
 * Site-001 (Fairlands): ESP32 LD2410C nodes (MQTT)
 * Other sites: BMS-driven focus room data via Supabase
 */

import { FocusRoomGrid } from "./FocusRoomCard";

// ---------------------------------------------------------------------------
// Site focus room configuration
// ---------------------------------------------------------------------------

const SITE_FOCUS_ROOMS: Record<string, Array<{ roomCode: string; label: string }>> = {
  // Fairlands — ESP32 MQTT nodes
  "site-001": [
    { roomCode: "FA2-1Q4-FR25", label: "FA2-1Q4-FR25" },
  ],
  // Sandton — one focus room per floor (L0, L1, L2)
  "site-002": [
    { roomCode: "FR-L0", label: "FR-L0" },
    { roomCode: "FR-L1", label: "FR-L1" },
    { roomCode: "FR-L2", label: "FR-L2" },
  ],
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SpaceOptimizationPageProps {
  siteId: string;
}

export function SpaceOptimizationPage({ siteId }: SpaceOptimizationPageProps) {
  const rooms = SITE_FOCUS_ROOMS[siteId] ?? [];

  return (
    <div
      style={{
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 20,
        minHeight: "calc(100vh - 180px)",
      }}
    >
      {/* Page header */}
      <div>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "var(--color-text)" }}>
          Focus Room Status
        </h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
          Real-time occupancy for all focus rooms on this site.
        </p>
      </div>

      {/* Focus room grid */}
      {rooms.length > 0 ? (
        <FocusRoomGrid siteId={siteId} rooms={rooms} />
      ) : (
        <div
          style={{
            border: "1px solid var(--color-sentinel-border)",
            borderRadius: 8,
            padding: "24px",
            textAlign: "center",
            color: "var(--color-text-muted)",
            fontSize: 13,
          }}
        >
          No focus rooms configured for this site yet.
        </div>
      )}
    </div>
  );
}
