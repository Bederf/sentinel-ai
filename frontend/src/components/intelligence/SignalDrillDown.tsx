/**
 * SignalDrillDown — Full context panel for a single signal.
 *
 * Replaces RoomDetailPanel when a signal is tapped. Shows full summary,
 * related signals timeline, evidence basis, suggested action, and
 * optional cluster info.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { ConciergeRoom, ConciergeSignalDetail, ConciergeSignalSummary } from "../../lib/api";
import { conciergeApi } from "../../lib/api";

// ---- Severity badge colours ----

const SEVERITY_BADGE: Record<string, { bg: string; text: string }> = {
  low: { bg: "rgba(46,204,113,0.15)", text: "var(--color-sentinel-green)" },
  medium: { bg: "rgba(241,196,15,0.15)", text: "var(--color-sentinel-amber)" },
  high: { bg: "rgba(230,126,34,0.15)", text: "var(--color-sentinel-amber)" },
  critical: { bg: "rgba(231,76,60,0.15)", text: "var(--color-sentinel-red)" },
};

// ---- Signal type labels (shared with RoomDetailPanel) ----

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

function compactRoomId(value: string): string {
  const raw = value.trim();
  if (!raw) return raw;
  return raw.replace(/^S\d{3}-/i, "");
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatAbsoluteDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-ZA", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type ThreadMessage = {
  from_name?: string;
  from_email?: string;
  sent_at?: string;
  to?: string[];
  cc?: string[];
  subject?: string;
  body_plain?: string;
};

function threadMessages(detail: ConciergeSignalDetail): ThreadMessage[] {
  const raw = detail.metadata?.thread_messages;
  if (!Array.isArray(raw)) return [];
  const messages = raw.filter((item): item is ThreadMessage => typeof item === "object" && item !== null);
  return [...messages].sort((left, right) => {
    const leftTime = left.sent_at ? new Date(left.sent_at).getTime() : Number.MAX_SAFE_INTEGER;
    const rightTime = right.sent_at ? new Date(right.sent_at).getTime() : Number.MAX_SAFE_INTEGER;
    return leftTime - rightTime;
  });
}

function metadataString(detail: ConciergeSignalDetail, key: string): string | null {
  const value = detail.metadata?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function metadataNumber(detail: ConciergeSignalDetail, key: string): number | null {
  const value = detail.metadata?.[key];
  return typeof value === "number" ? value : null;
}

function formatLocalDate(value?: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-ZA", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatLocalTime(value?: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleTimeString("en-ZA", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatTimeRange(start?: string | null, end?: string | null): string | null {
  const from = formatLocalTime(start);
  const to = formatLocalTime(end);
  if (from && to) return `${from} – ${to}`;
  return from || to;
}

function GhostBookingSummary({ detail }: { detail: ConciergeSignalDetail }) {
  const organiser =
    metadataString(detail, "organiser_name") ||
    metadataString(detail, "organiser") ||
    metadataString(detail, "organiser_email") ||
    metadataString(detail, "organiserEmail");
  const bookingStart = metadataString(detail, "booking_start") || metadataString(detail, "start_time");
  const bookingEnd = metadataString(detail, "booking_end") || metadataString(detail, "end_time");
  const dateLabel = formatLocalDate(bookingStart);
  const timeLabel = formatTimeRange(bookingStart, bookingEnd);

  const rows = [
    { label: "Organiser", value: organiser },
    { label: "Booking date", value: dateLabel },
    { label: "Booking time", value: timeLabel },
  ].filter((row) => row.value);

  if (!rows.length) return null;

  return (
    <>
      <SectionTitle>Booking Details</SectionTitle>
      <div className="grid grid-cols-1 gap-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className="px-3 py-2 rounded text-xs"
            style={{ background: "rgba(148,163,184,0.08)", border: "1px solid rgba(148,163,184,0.14)" }}
          >
            <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{row.label}</div>
            <div className="text-gray-200 break-words whitespace-pre-wrap">{row.value}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function MetadataGrid({ detail }: { detail: ConciergeSignalDetail }) {
  const fromEmail = metadataString(detail, "from_email");
  const fromName = metadataString(detail, "from_name");
  const subject = metadataString(detail, "subject");
  const receivedAt = metadataString(detail, "received_at");
  const moduleLabel = detail.source_module || metadataString(detail, "source");

  const items = [
    { label: "From", value: [fromName, fromEmail].filter(Boolean).join(" ") || null },
    { label: "Subject", value: subject },
    { label: "Received", value: receivedAt ? formatAbsoluteDateTime(receivedAt) : null },
    { label: "Source", value: moduleLabel },
  ].filter((item) => item.value);

  if (!items.length) return null;

  return (
    <>
      <SectionTitle>Info</SectionTitle>
      <div className="grid grid-cols-1 gap-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="px-3 py-2 rounded text-xs"
            style={{ background: "rgba(148,163,184,0.08)", border: "1px solid rgba(148,163,184,0.14)" }}
          >
            <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{item.label}</div>
            <div className="text-gray-200 break-words whitespace-pre-wrap">{item.value}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function AffectedContext({ detail, roomId }: { detail: ConciergeSignalDetail; roomId: string }) {
  const logicalSiteId = metadataString(detail, "logical_site_id");
  const affectedAsset = compactRoomId(metadataString(detail, "room_id") || roomId);
  const items = [
    { label: "Affected Room", value: affectedAsset || null },
    { label: "Affected Site", value: logicalSiteId },
  ].filter((item) => item.value);

  if (!items.length) return null;

  return (
    <>
      <SectionTitle>Context</SectionTitle>
      <div className="grid grid-cols-1 gap-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="px-3 py-2 rounded text-xs"
            style={{ background: "rgba(236, 72, 153, 0.06)", border: "1px solid rgba(236, 72, 153, 0.14)" }}
          >
            <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{item.label}</div>
            <div className="text-gray-200 break-words whitespace-pre-wrap">{item.value}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function EmailThread({ detail }: { detail: ConciergeSignalDetail }) {
  const messages = threadMessages(detail);
  if (!messages.length) return null;

  return (
    <>
      <SectionTitle>Email Timeline</SectionTitle>
      <div className="relative pl-6 space-y-3">
        <div
          className="absolute left-[11px] top-2 bottom-2 w-px"
          style={{ background: "linear-gradient(180deg, rgba(59,130,246,0.45), rgba(59,130,246,0.08))" }}
        />
        {messages.map((message, index) => (
          <div
            key={`${message.sent_at || "msg"}-${index}`}
            className="relative px-3 py-3 rounded"
            style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.15)" }}
          >
            <div
              className="absolute -left-6 top-3 w-[14px] h-[14px] rounded-full"
              style={{ background: "#0d1117", border: "2px solid rgba(96,165,250,0.9)", boxShadow: "0 0 0 4px rgba(59,130,246,0.12)" }}
              aria-hidden="true"
            />
            <div className="space-y-1 text-xs text-gray-300">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[10px] uppercase tracking-[0.18em] text-blue-300/80">
                  {index === 0 ? "Initial Email" : `Reply ${index}`}
                </span>
                {message.sent_at ? (
                  <span className="text-[10px] text-gray-500">{formatAbsoluteDateTime(message.sent_at)}</span>
                ) : null}
              </div>
              {(message.from_name || message.from_email) && (
                <div>
                  <span className="text-gray-500">From:</span>{" "}
                  {[message.from_name, message.from_email].filter(Boolean).join(" ")}
                </div>
              )}
              {message.subject && (
                <div>
                  <span className="text-gray-500">Subject:</span> {message.subject}
                </div>
              )}
              {message.to?.length ? (
                <div>
                  <span className="text-gray-500">To:</span> {message.to.join(", ")}
                </div>
              ) : null}
              {message.cc?.length ? (
                <div>
                  <span className="text-gray-500">Cc:</span> {message.cc.join(", ")}
                </div>
              ) : null}
            </div>
            {message.body_plain && (
              <div
                className="mt-3 px-3 py-2 rounded text-xs leading-6 whitespace-pre-wrap"
                style={{ background: "rgba(15,23,42,0.75)", border: "1px solid rgba(148,163,184,0.12)", color: "var(--color-sentinel-text-secondary)" }}
              >
                {message.body_plain}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function RawContent({ detail }: { detail: ConciergeSignalDetail }) {
  const [expanded, setExpanded] = useState(false);
  if (!detail.raw_content) return null;
  return (
    <div className="space-y-2">
      <button
        onClick={() => setExpanded((current) => !current)}
        className="flex items-center justify-between w-full px-3 py-2 text-left text-xs font-medium rounded"
        style={{
          background: "rgba(148,163,184,0.08)",
          border: "1px solid rgba(148,163,184,0.16)",
          color: "var(--color-sentinel-text-secondary)",
        }}
        aria-expanded={expanded}
      >
        <span>Raw content</span>
        <span className="text-[10px] text-gray-400">{expanded ? "Hide" : "Show"}</span>
      </button>
      {expanded && (
        <div
          className="px-3 py-3 rounded text-xs leading-6 whitespace-pre-wrap"
          style={{ background: "rgba(15,23,42,0.75)", border: "1px solid rgba(148,163,184,0.12)", color: "#cbd5e1" }}
        >
          {detail.raw_content}
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="text-xs">
      <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{label}</div>
      <div className="text-sm font-semibold text-gray-100 leading-tight">{value}</div>
    </div>
  );
}

interface BlockBookingDetailProps {
  detail: ConciergeSignalDetail;
  siteId: string;
  roomId: string;
  signalId: string;
  onBack: () => void;
}

function BlockBookingDetail({ detail, siteId, roomId, signalId, onBack }: BlockBookingDetailProps) {
  const [processing, setProcessing] = useState<"resolve" | "archive" | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const organiserName =
    metadataString(detail, "organiser_name") ||
    metadataString(detail, "organiser") ||
    metadataString(detail, "organiserEmail");
  const organiserEmail =
    metadataString(detail, "organiser_email") || metadataString(detail, "organiserEmail");
  const meetingRoom =
    metadataString(detail, "room_name") ||
    metadataString(detail, "room_id") ||
    detail.location_ref?.split("/").filter(Boolean).pop() ||
    roomId;
  const meetingRoomLabel = compactRoomId(meetingRoom);
  const bookingDateValue = metadataString(detail, "booking_date");
  const meetingDateLabel = formatLocalDate(bookingDateValue);
  const startTime = metadataString(detail, "booking_start") || metadataString(detail, "start_time");
  const endTime = metadataString(detail, "booking_end") || metadataString(detail, "end_time");
  const meetingTimeLabel = formatTimeRange(startTime, endTime);
  const bookingCreatedLabel = detail.created_at ? formatAbsoluteDateTime(detail.created_at) : null;
  const roomsAffected = Array.isArray(detail.metadata?.rooms)
    ? detail.metadata.rooms.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0,
      )
    : [];
  const overlapCount =
    metadataNumber(detail, "room_count") ?? (roomsAffected.length ? roomsAffected.length : null);
  const sourceLabel = detail.source_module || metadataString(detail, "source");
  const building = metadataString(detail, "building");
  const floor = metadataString(detail, "floor");
  const buildingFloor = [building, floor].filter(Boolean).join(" · ");

  const optionalMeta = [
    overlapCount ? { label: "Overlap count", value: `${overlapCount} rooms` } : null,
    sourceLabel ? { label: "Source", value: sourceLabel } : null,
    buildingFloor ? { label: "Building · Floor", value: buildingFloor } : null,
    organiserEmail ? { label: "Organiser email", value: organiserEmail } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  const handleAction = async (mode: "resolve" | "archive") => {
    if (processing) return;
    setProcessing(mode);
    setFeedback(null);
    setError(null);
    try {
      await conciergeApi.resolveSignal(
        siteId,
        roomId,
        signalId,
        "resolved",
        mode === "resolve"
          ? "Resolved via block booking detail"
          : "Archived via block booking detail",
      );
      setFeedback(mode === "resolve" ? "Resolved" : "Archived");
      onBack();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update status");
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-gray-100">Block Booking Risk</p>
          <p className="text-[10px] text-gray-500 uppercase tracking-[0.3em] mt-1">
            Meeting room {meetingRoomLabel}
          </p>
        </div>
        {/* Severity is already shown in the panel header */}
      </div>

      <p className="text-xs text-gray-300 leading-relaxed">{detail.summary}</p>
      {detail.advisory_label && (
        <p className="text-[10px] italic text-yellow-400 uppercase tracking-[0.1em]">
          {detail.advisory_label}
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <DetailRow label="Organiser" value={organiserName || "Unknown organiser"} />
        <DetailRow label="Booking created" value={bookingCreatedLabel || "Unknown"} />
        <DetailRow label="Meeting date" value={meetingDateLabel || "Unscheduled"} />
        <DetailRow label="Meeting time" value={meetingTimeLabel || "Unknown"} />
      </div>

      {optionalMeta.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          {optionalMeta.map((item) => (
            <DetailRow key={item.label} label={item.label} value={item.value} />
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => void handleAction("resolve")}
          disabled={Boolean(processing)}
          className="px-4 py-2 text-xs font-semibold uppercase tracking-widest rounded border transition-colors"
          style={{
            background: processing === "resolve" ? "rgba(34,197,94,0.22)" : "rgba(16,185,129,0.15)",
            color: "var(--color-sentinel-green)",
            border: "1px solid rgba(16,185,129,0.4)",
          }}
        >
          {processing === "resolve" ? "Resolving…" : "Resolve"}
        </button>
        <button
          onClick={() => void handleAction("archive")}
          disabled={Boolean(processing)}
          className="px-4 py-2 text-xs font-semibold uppercase tracking-widest rounded border transition-colors"
          style={{
            background: processing === "archive" ? "rgba(239,68,68,0.22)" : "rgba(239,68,68,0.15)",
            color: "var(--color-sentinel-red)",
            border: "1px solid rgba(239,68,68,0.4)",
          }}
        >
          {processing === "archive" ? "Archiving…" : "Archive"}
        </button>
        {feedback && (
          <span className="text-[10px] text-green-300">{feedback} — closing panel…</span>
        )}
        {error && <span className="text-[10px] text-red-400">{error}</span>}
      </div>

      <RawContent detail={detail} />
    </div>
  );
}

// ---- Props ----

interface SignalDrillDownProps {
  siteId: string;
  roomId: string;
  signalId: string;
  room?: ConciergeRoom;
  onSignalSelect?: (signalId: string) => void;
  onBack: () => void;
  onResolved?: () => void;
}

type CategoryKey = "info" | "block" | "ghost";

function categoryFromSignalType(signalType: string): CategoryKey {
  if (signalType === "booking_conflict") return "block";
  if (signalType === "no_show_pattern" || signalType === "booking_no_show") return "ghost";
  return "info";
}

function categoryLabel(category: CategoryKey): string {
  if (category === "block") return "Block";
  if (category === "ghost") return "Ghost";
  return "Info";
}

function categoryOrder(category: CategoryKey): number {
  if (category === "block") return 0;
  if (category === "ghost") return 1;
  return 2;
}

function getSignalTimestamp(signal: ConciergeSignalSummary): number {
  const ts = new Date(signal.created_at).getTime();
  return Number.isFinite(ts) ? ts : 0;
}

// ---- Subcomponents ----

function SeverityBadge({ severity }: { severity: string }) {
  const style = SEVERITY_BADGE[severity] || SEVERITY_BADGE.low;
  return (
    <span
      className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full font-medium"
      style={{ background: style.bg, color: style.text }}
    >
      {severity}
    </span>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[10px] uppercase tracking-wider mb-2 mt-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
      {children}
    </h4>
  );
}

function RelatedTimeline({ detail }: { detail: ConciergeSignalDetail }) {
  if (!detail.related_signals?.length) return null;

  // Collapse repetitive related signals (common for booking-driven ghost findings).
  const grouped = new Map<string, { id: string; created_at: string; summary: string; count: number }>();
  for (const rs of detail.related_signals) {
    const key = `${rs.signal_type}::${rs.summary}`;
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, { id: rs.id, created_at: rs.created_at, summary: rs.summary, count: 1 });
      continue;
    }
    existing.count += 1;
    // Keep the most recent timestamp for display
    if (new Date(rs.created_at).getTime() > new Date(existing.created_at).getTime()) {
      existing.created_at = rs.created_at;
      existing.id = rs.id;
    }
  }

  const items = Array.from(grouped.values()).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <>
      <SectionTitle>Related Signals</SectionTitle>
      <div className="space-y-1.5">
        {items.map((rs) => (
          <div
            key={rs.id}
            className="flex items-start gap-2 px-2 py-1.5 rounded text-xs"
            style={{
              background: rs.id === detail.id ? "rgba(59,130,246,0.1)" : "transparent",
              borderLeft: rs.id === detail.id ? "2px solid var(--color-sentinel-blue)" : "2px solid transparent",
            }}
          >
            <span className="text-gray-500 flex-shrink-0 w-12">{relativeTime(rs.created_at)}</span>
            <span className="text-gray-300 line-clamp-1 flex-1 min-w-0">{rs.summary}</span>
            {rs.count > 1 && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0"
                style={{ background: "rgba(255,255,255,0.08)", color: "#a0a0a0" }}
                title="Collapsed duplicates"
              >
                x{rs.count}
              </span>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function EvidenceList({ items }: { items: string[] }) {
  if (!items?.length) return null;
  return (
    <>
      <SectionTitle>Evidence Basis</SectionTitle>
      <ul className="space-y-1 text-xs text-gray-400">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-gray-600 mt-0.5">-</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function ClusterInfo({ cluster }: { cluster: NonNullable<ConciergeSignalDetail["issue_cluster"]> }) {
  return (
    <>
      <SectionTitle>Linked Issue Cluster</SectionTitle>
      <div
        className="px-3 py-2 rounded text-xs"
        style={{ background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.15)" }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-gray-200 font-medium">{cluster.title}</span>
          <SeverityBadge severity={cluster.severity} />
        </div>
        <span className="text-[10px] text-gray-500">State: {cluster.cluster_state}</span>
      </div>
    </>
  );
}

// ---- Main component ----

export function SignalDrillDown({ siteId, roomId, signalId, room, onSignalSelect, onBack, onResolved }: SignalDrillDownProps) {
  const [detail, setDetail] = useState<ConciergeSignalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    conciergeApi
      .getSignalDetail(siteId, roomId, signalId)
      .then((data) => setDetail(data))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load signal"))
      .finally(() => setLoading(false));
  }, [siteId, roomId, signalId]);

  const typeLabel = detail
    ? SIGNAL_TYPE_LABELS[detail.signal_type] || detail.signal_type.replace(/_/g, " ")
    : "";
  const isBlockBooking = detail?.signal_type === "booking_conflict";
  const isGhostBooking =
    detail?.signal_type === "no_show_pattern" || detail?.signal_type === "booking_no_show";

  const handleResolve = useCallback(async () => {
    if (processing) return;
    setProcessing(true);
    setActionError(null);
    try {
      await conciergeApi.resolveSignal(siteId, roomId, signalId, "resolved", "Resolved via signal drill-down");
      onResolved?.();
      onBack();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unable to resolve signal");
    } finally {
      setProcessing(false);
    }
  }, [processing, siteId, roomId, signalId, onBack, onResolved]);

  const categorySignals = new Map<CategoryKey, ConciergeSignalSummary[]>();
  for (const signal of room?.signals || []) {
    const key = categoryFromSignalType(signal.signal_type);
    const existing = categorySignals.get(key);
    if (existing) {
      existing.push(signal);
    } else {
      categorySignals.set(key, [signal]);
    }
  }

  const categoryTabs = Array.from(categorySignals.entries())
    .map(([key, signals]) => ({ key, signals }))
    .sort((left, right) => categoryOrder(left.key) - categoryOrder(right.key));

  const activeCategory = detail ? categoryFromSignalType(detail.signal_type) : null;

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
        className="flex items-center gap-2 px-4 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <button
          onClick={onBack}
          className="p-1 rounded-lg transition-colors"
          style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-secondary)" }}
          aria-label="Back to room"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <span className="text-xs text-gray-100 font-medium truncate block">{typeLabel}</span>
          <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>{compactRoomId(roomId)}</span>
        </div>
        {detail && (
          <button
            type="button"
            onClick={() => void handleResolve()}
            disabled={processing}
            className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest rounded-lg border transition-colors"
            style={{
              background: processing ? "rgba(34,197,94,0.22)" : "rgba(16,185,129,0.12)",
              color: "var(--color-sentinel-green)",
              borderColor: "rgba(16,185,129,0.35)",
              opacity: processing ? 0.75 : 1,
            }}
            title="Resolve and remove from the map"
          >
            {processing ? "Resolving…" : "Resolve"}
          </button>
        )}
        {detail && <SeverityBadge severity={detail.severity} />}
      </div>
      {categoryTabs.length > 0 && (
        <div
          className="px-4 py-2.5 flex items-center gap-2 flex-wrap"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}
        >
          {categoryTabs.map((tab) => {
            const isActive = activeCategory === tab.key;
            const latestSignal = [...tab.signals].sort((a, b) => getSignalTimestamp(b) - getSignalTimestamp(a))[0];
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => {
                  if (latestSignal) onSignalSelect?.(latestSignal.id);
                }}
                className="px-2.5 py-1 text-[10px] rounded-full border transition-colors uppercase tracking-wider font-medium"
                style={{
                  background: isActive ? "rgba(59,130,246,0.22)" : "rgba(148,163,184,0.10)",
                  borderColor: isActive ? "rgba(59,130,246,0.55)" : "rgba(148,163,184,0.25)",
                  color: isActive ? "var(--color-sentinel-blue)" : "var(--color-sentinel-text-secondary)",
                }}
              >
                {categoryLabel(tab.key)} ({tab.signals.length})
              </button>
            );
          })}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <p className="text-xs text-red-400 text-center py-8">{error}</p>
        ) : detail ? (
          isBlockBooking ? (
            <BlockBookingDetail
              detail={detail}
              siteId={siteId}
              roomId={roomId}
              signalId={signalId}
              onBack={onBack}
            />
          ) : (
            <>
              {actionError && (
                <div className="mb-3 px-3 py-2 rounded text-xs" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.18)", color: "var(--color-sentinel-red)" }}>
                  {actionError}
                </div>
              )}
              {/* Full summary */}
              <p className="text-sm leading-relaxed" style={{ color: "var(--color-sentinel-text-primary)" }}>{detail.summary}</p>

              {/* Confidence + time */}
              <div className="flex items-center gap-3 mt-3 text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <span>Confidence: {(detail.confidence * 100).toFixed(0)}%</span>
                <span>{relativeTime(detail.created_at)}</span>
              </div>

              <AffectedContext detail={detail} roomId={roomId} />

              {isGhostBooking && <GhostBookingSummary detail={detail} />}

              <MetadataGrid detail={detail} />

              <EmailThread detail={detail} />

              {/* Related signals timeline */}
              <RelatedTimeline detail={detail} />

              {/* Evidence basis */}
              <EvidenceList items={detail.evidence_basis} />

              <RawContent detail={detail} />

              {/* Suggested action */}
              {detail.suggested_action && (
                <>
                  <SectionTitle>Suggested Action</SectionTitle>
                  <div
                    className="px-3 py-2.5 rounded text-xs"
                    style={{ background: "rgba(241,196,15,0.08)", border: "1px solid rgba(241,196,15,0.15)" }}
                  >
                    <p className="text-gray-300 mb-2">{detail.suggested_action}</p>
                    <p className="text-[10px] text-yellow-600 italic">
                      {detail.advisory_label || "For awareness only. Act at your discretion."}
                    </p>
                  </div>
                </>
              )}

              {/* Cluster info */}
              {detail.issue_cluster && <ClusterInfo cluster={detail.issue_cluster} />}
            </>
          )
        ) : null}
      </div>
    </div>
  );
}
