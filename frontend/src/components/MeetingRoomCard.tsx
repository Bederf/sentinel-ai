/**
 * MeetingRoomCard — Live occupancy status for a meeting room.
 *
 * Shows: room label, occupied/free state, last-seen timestamp.
 * Styled after FocusRoomCard (red=occupied, grey=free).
 */

import { useState, useEffect } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { RoomOccupancyStatus } from "../lib/api";
import { spaceApi } from "../lib/api";

interface MeetingRoomCardProps {
  siteId: string;
  roomCode: string;
  roomLabel: string;
}

function formatLastSeen(ts: string): string {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  const m = Math.floor(diff / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

export function MeetingRoomCard({ siteId, roomCode, roomLabel }: MeetingRoomCardProps) {
  const [status, setStatus] = useState<RoomOccupancyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setLoading(true);
    setStatus(null);
    let cancelled = false;
    spaceApi.getRoomOccupancy(siteId, roomCode).then((data) => {
      if (cancelled) return;
      setStatus(data.length > 0 ? data[0] : null);
      setLoading(false);
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [siteId, roomCode, tick]);

  // Refresh every 30s
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const occupied = status?.occupied ?? false;
  const lastSeen = status?.last_seen ?? null;

  // Visual style matches FocusRoomCard
  let statusColor = "var(--color-text-muted)";
  let StatusIcon = CheckCircle2;
  let statusLabel = "Free";
  if (loading) {
    statusLabel = "Loading...";
    statusColor = "var(--color-text-muted)";
  } else if (occupied) {
    statusColor = "var(--color-sentinel-red)";
    StatusIcon = AlertCircle;
    statusLabel = "Occupied";
  } else {
    statusColor = "var(--color-text-muted)";
    StatusIcon = CheckCircle2;
    statusLabel = "Free";
  }

  return (
    <div style={{
      border: `1.5px solid ${statusColor}`,
      borderRadius: 8,
      padding: "12px 16px",
      background: loading ? "transparent" : `color-mix(in srgb, ${statusColor} 6%, transparent)`,
      minWidth: 160,
      display: "flex",
      flexDirection: "column",
      gap: 6,
    }}>
      {/* Room label */}
      <span style={{ fontWeight: 600, fontSize: 14, color: "var(--color-text)" }}>
        {roomLabel}
      </span>

      {/* Status line */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <StatusIcon size={16} color={statusColor} />
        <span style={{ color: statusColor, fontWeight: 500, fontSize: 13 }}>
          {statusLabel}
        </span>
      </div>

      {/* Last seen */}
      {lastSeen && !loading && (
        <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
          {formatLastSeen(lastSeen)}
        </span>
      )}
    </div>
  );
}
