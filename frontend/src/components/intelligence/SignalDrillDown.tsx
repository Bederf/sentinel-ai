/**
 * SignalDrillDown — Full context panel for a single signal.
 *
 * Replaces RoomDetailPanel when a signal is tapped. Shows full summary,
 * related signals timeline, evidence basis, suggested action, and
 * optional cluster info.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { ConciergeSignalDetail } from "../../lib/api";
import { conciergeApi } from "../../lib/api";

// ---- Severity badge colours ----

const SEVERITY_BADGE: Record<string, { bg: string; text: string }> = {
  low: { bg: "rgba(46,204,113,0.15)", text: "#2ecc71" },
  medium: { bg: "rgba(241,196,15,0.15)", text: "#f1c40f" },
  high: { bg: "rgba(230,126,34,0.15)", text: "#e67e22" },
  critical: { bg: "rgba(231,76,60,0.15)", text: "#e74c3c" },
};

// ---- Signal type labels (shared with RoomDetailPanel) ----

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  booking_conflict: "Block Booking",
  booking_saturation: "Booking Saturation",
  no_show_pattern: "Ghost Booking",
  complaint_email: "Complaint",
  escalation_email: "Escalation",
  observation_email: "Observation",
  hvac_fault: "HVAC Fault",
  maintenance_request: "Maintenance",
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ---- Props ----

interface SignalDrillDownProps {
  siteId: string;
  roomId: string;
  signalId: string;
  onBack: () => void;
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
    <h4 className="text-[10px] uppercase tracking-wider text-gray-500 mb-2 mt-4">
      {children}
    </h4>
  );
}

function RelatedTimeline({ detail }: { detail: ConciergeSignalDetail }) {
  if (!detail.related_signals?.length) return null;
  return (
    <>
      <SectionTitle>Related Signals</SectionTitle>
      <div className="space-y-1.5">
        {detail.related_signals.map((rs) => (
          <div
            key={rs.id}
            className="flex items-start gap-2 px-2 py-1.5 rounded text-xs"
            style={{
              background: rs.id === detail.id ? "rgba(59,130,246,0.1)" : "transparent",
              borderLeft: rs.id === detail.id ? "2px solid #3B82F6" : "2px solid transparent",
            }}
          >
            <span className="text-gray-500 flex-shrink-0 w-12">{relativeTime(rs.created_at)}</span>
            <span className="text-gray-300 line-clamp-1">{rs.summary}</span>
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

export function SignalDrillDown({ siteId, roomId, signalId, onBack }: SignalDrillDownProps) {
  const [detail, setDetail] = useState<ConciergeSignalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div
      className="absolute top-0 right-0 h-full w-[380px] max-w-full flex flex-col z-30 animate-slide-in-right"
      style={{
        background: "#0d1117",
        borderLeft: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}
      >
        <button
          onClick={onBack}
          className="p-1 rounded hover:bg-gray-800 transition-colors text-gray-500 hover:text-gray-300"
          aria-label="Back to room"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <span className="text-xs text-gray-100 font-medium truncate block">{typeLabel}</span>
          <span className="text-[10px] text-gray-500">{roomId}</span>
        </div>
        {detail && <SeverityBadge severity={detail.severity} />}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <p className="text-xs text-red-400 text-center py-8">{error}</p>
        ) : detail ? (
          <>
            {/* Full summary */}
            <p className="text-sm text-gray-200 leading-relaxed">{detail.summary}</p>

            {/* Confidence + time */}
            <div className="flex items-center gap-3 mt-3 text-[10px] text-gray-500">
              <span>Confidence: {(detail.confidence * 100).toFixed(0)}%</span>
              <span>{relativeTime(detail.created_at)}</span>
            </div>

            {/* Related signals timeline */}
            <RelatedTimeline detail={detail} />

            {/* Evidence basis */}
            <EvidenceList items={detail.evidence_basis} />

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
        ) : null}
      </div>
    </div>
  );
}
