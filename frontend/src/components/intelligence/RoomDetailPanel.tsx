/**
 * RoomDetailPanel — Slide-in panel showing signal timeline for a room.
 *
 * Opens on room tap from ConciergeMap. Displays signal cards with
 * domain colour dots, type labels, summaries, and relative timestamps.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ConciergeRoom, ConciergeSignalSummary } from "../../lib/api";
import { conciergeApi } from "../../lib/api";

// ---- Signal type display labels ----

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  booking_conflict: "Block Booking Risk",
  booking_saturation: "Booking Saturation",
  no_show_pattern: "Ghost Booking",
  complaint_email: "Complaint",
  escalation_email: "Escalation",
  observation_email: "Observation",
  hvac_fault: "HVAC Fault",
  maintenance_request: "Maintenance",
};

// ---- Domain colour dots ----

const SIGNAL_DOMAIN_COLORS: Record<string, string> = {
  booking_conflict: "#f4900c",
  booking_saturation: "#f4900c",
  no_show_pattern: "#e74c3c",
  complaint_email: "#4a9eff",
  escalation_email: "#4a9eff",
  observation_email: "#4a9eff",
  hvac_fault: "#e74c3c",
  maintenance_request: "#f1c40f",
};

// ---- Relative time helper ----

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ---- Props ----

interface RoomDetailPanelProps {
  siteId: string;
  room: ConciergeRoom;
  onClose: () => void;
  onSignalSelect: (signalId: string) => void;
}

// ---- Signal card subcomponent ----

function SignalCard({
  signal,
  repeatCount,
  onSelect,
}: {
  signal: ConciergeSignalSummary;
  repeatCount: number;
  onSelect: () => void;
}) {
  const color = SIGNAL_DOMAIN_COLORS[signal.signal_type] || "#8b7fd4";
  const label = SIGNAL_TYPE_LABELS[signal.signal_type] || signal.signal_type.replace(/_/g, " ");

  return (
    <button
      onClick={onSelect}
      className="w-full text-left px-3 py-2.5 rounded-lg border transition-colors"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        borderColor: "var(--color-sentinel-border)",
      }}
    >
      <div className="flex items-start gap-2">
        {/* Domain colour dot */}
        <div
          className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        <div className="flex-1 min-w-0">
          {/* Type label + repeat badge */}
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[10px] uppercase tracking-wider font-medium" style={{ color }}>
              {label}
            </span>
            {repeatCount > 1 && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded-full"
                style={{ background: "rgba(255,255,255,0.08)", color: "#a0a0a0" }}
              >
                x{repeatCount}
              </span>
            )}
          </div>
          {/* Summary text */}
          <p className="text-xs line-clamp-2" style={{ color: "var(--color-sentinel-text-primary)" }}>{signal.summary}</p>
          {/* Footer — when */}
          <p className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {relativeTime(signal.created_at)}
          </p>
        </div>
      </div>
    </button>
  );
}

// ---- Main panel ----

export function RoomDetailPanel({ siteId, room, onClose, onSignalSelect }: RoomDetailPanelProps) {
  const [signals, setSignals] = useState<ConciergeSignalSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    conciergeApi
      .getRoomSignals(siteId, room.room_id)
      .then((data) => setSignals(data || []))
      .catch(() => setSignals(room.signals || []))
      .finally(() => setLoading(false));
  }, [siteId, room.room_id, room.signals]);

  // Count repeats per signal_type
  const typeCounts: Record<string, number> = {};
  for (const s of signals) {
    typeCounts[s.signal_type] = (typeCounts[s.signal_type] || 0) + 1;
  }

  const latestTime = room.latest_signal_at ? relativeTime(room.latest_signal_at) : "n/a";

  return (
    <div
      className="absolute top-0 right-0 h-full w-[380px] max-w-full flex flex-col z-30 animate-slide-in-right"
      style={{
        background: "var(--color-sentinel-bg-canvas)",
        borderLeft: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="min-w-0">
          <h3 className="text-sm font-semibold truncate" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {room.friendly_name || room.room_id}
          </h3>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ background: "rgba(59,130,246,0.15)", color: "#60a5fa" }}
            >
              {room.signal_count} signal{room.signal_count !== 1 ? "s" : ""}
            </span>
            <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>{latestTime}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg transition-colors"
          style={{ color: "var(--color-sentinel-text-secondary)", background: "var(--color-sentinel-bg-secondary)" }}
          aria-label="Close panel"
        >
          <X size={16} />
        </button>
      </div>

      {/* Body — scrollable signal list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : signals.length === 0 ? (
          <p className="text-xs text-center py-8" style={{ color: "var(--color-sentinel-text-secondary)" }}>No signals for this room</p>
        ) : (
          signals.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              repeatCount={typeCounts[signal.signal_type] || 1}
              onSelect={() => onSignalSelect(signal.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
