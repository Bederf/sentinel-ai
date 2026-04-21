/**
 * FocusRoomCard — Real-time focus room occupancy status.
 *
 * Displays: room name, occupancy state, session duration, red-light overstay indicator.
 * Designed for Sandton site (site-002) focus rooms.
 */

import { useState, useEffect } from "react";
import { AlertCircle, CheckCircle2, Clock, User } from "lucide-react";
import type { FocusSession } from "../lib/api";
import { spaceApi } from "../lib/api";

interface FocusRoomCardProps {
  siteId: string;
  roomCode: string;
  roomLabel: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem > 0 ? `${h}h ${rem}m` : `${h}h`;
}

function elapsed(startTime: string): number {
  return Math.floor((Date.now() - new Date(startTime).getTime()) / 1000);
}

// ---------------------------------------------------------------------------
// Single card
// ---------------------------------------------------------------------------

function FocusRoomCard({ siteId, roomCode, roomLabel }: FocusRoomCardProps) {
  const [session, setSession] = useState<FocusSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  // Re-fetch whenever siteId/roomCode changes or every 30s for updates
  useEffect(() => {
    setLoading(true);
    setSession(null);
    let cancelled = false;
    spaceApi.getFocusSessions(siteId, roomCode).then((data) => {
      if (cancelled) return;
      // Pick the most recent session (active first)
      const active = data.sessions.find((s) => s.is_active) ?? null;
      setSession(active);
      setLoading(false);
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [siteId, roomCode, tick]);

  // Refresh tick every 30s
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const isActive = session?.is_active ?? false;
  const redLight = session?.red_light_on ?? false;
  const extended = session?.extended_use ?? false;
  const duration = isActive && session
    ? session.duration_seconds + elapsed(session.start_time)
    : session?.duration_seconds ?? 0;

  // Status colour
  let statusColor = "var(--color-text-muted)";
  let StatusIcon = CheckCircle2;
  let statusLabel = "Vacant";
  if (isActive) {
    if (redLight) {
      statusColor = "var(--color-sentinel-red)";
      StatusIcon = AlertCircle;
      statusLabel = "Overstay";
    } else if (extended) {
      statusColor = "var(--color-sentinel-amber)";
      StatusIcon = Clock;
      statusLabel = "In use";
    } else {
      statusColor = "var(--color-sentinel-green)";
      StatusIcon = CheckCircle2;
      statusLabel = "In use";
    }
  }

  return (
    <div
      style={{
        border: `1.5px solid ${isActive ? statusColor : "var(--color-sentinel-border)"}`,
        borderRadius: 8,
        padding: "12px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        background: isActive ? `color-mix(in srgb, ${statusColor} 6%, transparent)` : "transparent",
        transition: "all 0.3s ease",
        minWidth: 180,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <User size={14} color={statusColor} />
          <span style={{ fontWeight: 600, fontSize: 13, color: "var(--color-text)" }}>{roomLabel}</span>
        </div>
        {redLight && (
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: "var(--color-sentinel-red)",
              boxShadow: "0 0 8px var(--color-sentinel-red)",
              animation: "pulse 1.5s infinite",
            }}
          />
        )}
      </div>

      {/* Status */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusIcon size={13} color={statusColor} />
        <span style={{ fontSize: 12, color: statusColor, fontWeight: 500 }}>{statusLabel}</span>
      </div>

      {/* Duration */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <Clock size={12} color="var(--color-text-muted)" />
        <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          {loading && !session ? "—" : formatDuration(duration)}
        </span>
        {isActive && (
          <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>
            (elapsed)
          </span>
        )}
      </div>

      {/* Sensor */}
      {session && (
        <div style={{ fontSize: 10, color: "var(--color-text-muted)" }}>
          {session.sensor_id}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Focus room grid for a site
// ---------------------------------------------------------------------------

interface FocusRoomGridProps {
  siteId: string;
  /** List of { roomCode, label } pairs to display */
  rooms: Array<{ roomCode: string; label: string }>;
}

export function FocusRoomGrid({ siteId, rooms }: FocusRoomGridProps) {
  const [analytics, setAnalytics] = useState<{ total: number; active: number; extended: number } | null>(null);

  useEffect(() => {
    spaceApi.getFocusAnalytics(siteId).then((a) => {
      setAnalytics({ total: a.total_sessions, active: a.active_sessions, extended: a.extended_use_count });
    }).catch(() => {});
  }, [siteId]);

  return (
    <div>
      {/* Summary bar */}
      <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 12, color: "var(--color-text-muted)" }}>
        {analytics && (
          <>
            <span><strong style={{ color: "var(--color-text)" }}>{analytics.total}</strong> total sessions</span>
            <span><strong style={{ color: "var(--color-sentinel-green)" }}>{analytics.active}</strong> currently active</span>
            <span><strong style={{ color: "var(--color-sentinel-amber)" }}>{analytics.extended}</strong> extended-use</span>
          </>
        )}
      </div>

      {/* Room cards */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {rooms.map((room) => (
          <FocusRoomCard key={room.roomCode} siteId={siteId} roomLabel={room.label ?? room.roomCode} {...room} />
        ))}
      </div>
    </div>
  );
}
