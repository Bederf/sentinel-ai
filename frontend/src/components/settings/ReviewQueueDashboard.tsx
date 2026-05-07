/**
 * Review Queue Dashboard
 *
 * Phase 162: Semantic Control Foundation — Plan 05.
 * Human-in-the-loop review interface for semantic classification decisions.
 * Facility managers review, approve, reject, and override classifications.
 */

import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { ClipboardCheck, AlertTriangle, CheckCircle, XCircle, X } from "lucide-react";
import { reviewQueueApi } from "../../lib/api/reviewQueue";
import type { ReviewQueueEntry, ReviewQueueStats } from "../../lib/api/reviewQueue";

interface ReviewQueueDashboardProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: (message: string) => void;
}

type SafetyClass = "HIGH" | "MEDIUM" | "LOW";
type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";

// --- Modal state shapes ---

interface ApproveModalState {
  open: boolean;
  entryId: string | null;
  notes: string;
}

interface RejectModalState {
  open: boolean;
  entryId: string | null;
  reason: string;
  notes: string;
}

interface BulkConfirmModalState {
  open: boolean;
  eligibleIds: string[];
}

// --- Style helpers ---

function safetyBadgeStyle(safetyClass: string): React.CSSProperties {
  if (safetyClass === "HIGH") {
    return { background: "rgba(239,68,68,0.15)", color: "var(--color-sentinel-red)", border: "1px solid rgba(239,68,68,0.3)" };
  }
  if (safetyClass === "MEDIUM") {
    return { background: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245,158,11,0.3)" };
  }
  return { background: "rgba(34,197,94,0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(34,197,94,0.3)" };
}

function confidenceBadgeStyle(confidenceLevel: string): React.CSSProperties {
  if (confidenceLevel === "HIGH") {
    return { background: "rgba(34,197,94,0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(34,197,94,0.3)" };
  }
  if (confidenceLevel === "MEDIUM") {
    return { background: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245,158,11,0.3)" };
  }
  return { background: "rgba(239,68,68,0.15)", color: "var(--color-sentinel-red)", border: "1px solid rgba(239,68,68,0.3)" };
}

const textPrimary: React.CSSProperties = { color: "var(--color-sentinel-text-primary)" };
const textSecondary: React.CSSProperties = { color: "var(--color-sentinel-text-secondary)" };
const borderStyle = { borderColor: "var(--color-sentinel-border)" };
const inputStyle: React.CSSProperties = {
  background: "var(--color-sentinel-bg-secondary)",
  border: "1px solid var(--glass-border)",
  color: "var(--color-sentinel-text-primary)",
  width: "100%",
  borderRadius: "0.375rem",
  padding: "0.5rem 0.75rem",
  fontSize: "0.875rem",
};
const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  resize: "vertical",
  minHeight: "72px",
};

// --- Inline portal modal wrapper ---

function ModalPortal({ children }: { children: React.ReactNode }) {
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      {children}
    </div>,
    document.body,
  );
}

// --- Main component ---

export function ReviewQueueDashboard({
  siteId = "site-002",
  onError,
  onSuccess,
}: ReviewQueueDashboardProps) {
  const [entries, setEntries] = useState<ReviewQueueEntry[]>([]);
  const [stats, setStats] = useState<ReviewQueueStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedSite, setSelectedSite] = useState(siteId);
  const [safetyFilter, setSafetyFilter] = useState<SafetyClass | "">("");
  const [sortByPriority, setSortByPriority] = useState(true);

  // Modal state
  const [approveModal, setApproveModal] = useState<ApproveModalState>({
    open: false,
    entryId: null,
    notes: "",
  });
  const [rejectModal, setRejectModal] = useState<RejectModalState>({
    open: false,
    entryId: null,
    reason: "",
    notes: "",
  });
  const [bulkModal, setBulkModal] = useState<BulkConfirmModalState>({
    open: false,
    eligibleIds: [],
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [entriesData, statsData] = await Promise.all([
        reviewQueueApi.getPending({
          site_id: selectedSite,
          safety_class: safetyFilter || undefined,
          limit: 200,
        }),
        reviewQueueApi.getStats(selectedSite),
      ]);
      const sorted = sortByPriority
        ? [...entriesData].sort((a, b) => a.priority - b.priority)
        : entriesData;
      setEntries(sorted);
      setStats(statsData);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to load review queue");
    } finally {
      setLoading(false);
    }
  }, [selectedSite, safetyFilter, sortByPriority, onError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // --- Modal open handlers ---

  const handleApprove = (entryId: string) => {
    setApproveModal({ open: true, entryId, notes: "" });
  };

  const handleReject = (entryId: string) => {
    setRejectModal({ open: true, entryId, reason: "", notes: "" });
  };

  const handleBulkApprove = () => {
    const eligible = entries.filter(
      (e) => e.confidence_score >= 0.7 && e.safety_class === "LOW",
    );
    if (eligible.length === 0) {
      onError?.("No eligible entries (HIGH confidence + LOW safety) found for bulk approval.");
      return;
    }
    setBulkModal({ open: true, eligibleIds: eligible.map((e) => e.id) });
  };

  // --- Modal submit handlers ---

  const submitApprove = async () => {
    if (!approveModal.entryId) return;
    try {
      await reviewQueueApi.approve(approveModal.entryId, approveModal.notes);
      onSuccess?.("Classification approved.");
      setApproveModal({ open: false, entryId: null, notes: "" });
      await loadData();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Approval failed");
    }
  };

  const submitReject = async () => {
    if (!rejectModal.entryId || !rejectModal.reason.trim()) return;
    try {
      await reviewQueueApi.reject(rejectModal.entryId, rejectModal.reason, rejectModal.notes);
      onSuccess?.("Classification rejected.");
      setRejectModal({ open: false, entryId: null, reason: "", notes: "" });
      await loadData();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Rejection failed");
    }
  };

  const submitBulkApprove = async () => {
    try {
      const result = await reviewQueueApi.bulkApprove(bulkModal.eligibleIds);
      onSuccess?.(result.message);
      setBulkModal({ open: false, eligibleIds: [] });
      await loadData();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Bulk approval failed");
    }
  };

  const confidenceLevels: ConfidenceLevel[] = ["HIGH", "MEDIUM", "LOW"];
  const safetyClasses: SafetyClass[] = ["HIGH", "MEDIUM", "LOW"];

  return (
    <>
      <div className="glass-panel overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b" style={borderStyle}>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(99,102,241,0.15)", color: "var(--color-sentinel-blue)" }}
              >
                <ClipboardCheck className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold" style={textPrimary}>
                  Semantic Classification Review Queue
                </h2>
                <p className="text-sm" style={textSecondary}>
                  Review AI classifications before enabling autonomous control
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleBulkApprove}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{ background: "rgba(34,197,94,0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(34,197,94,0.3)" }}
            >
              <CheckCircle className="h-3 w-3" />
              Bulk Approve Safe
            </button>
          </div>
        </div>

        {/* Stats Row */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b" style={borderStyle}>
            <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <p className="text-xs mb-1" style={textSecondary}>Total Pending</p>
              <p className="text-2xl font-bold" style={textPrimary}>{stats.total_pending}</p>
            </div>
            <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <p className="text-xs mb-1" style={textSecondary}>High Priority</p>
              <p className="text-2xl font-bold" style={{ color: "var(--color-sentinel-red)" }}>{stats.high_priority_count}</p>
            </div>
            <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <p className="text-xs mb-1" style={textSecondary}>Avg Age (hrs)</p>
              <p className="text-2xl font-bold" style={textPrimary}>{stats.avg_age_hours.toFixed(1)}</p>
            </div>
            <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
              <p className="text-xs mb-2" style={textSecondary}>By Safety Class</p>
              <div className="flex flex-wrap gap-1">
                {safetyClasses.map((cls) => (
                  <span key={cls} className="px-1.5 py-0.5 rounded text-xs font-medium" style={safetyBadgeStyle(cls)}>
                    {cls}: {stats.by_safety_class[cls] ?? 0}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 p-4 border-b" style={borderStyle}>
          <div>
            <label className="block text-xs mb-1" style={textSecondary}>Site</label>
            <select
              value={selectedSite}
              onChange={(e) => setSelectedSite(e.target.value)}
              className="rounded px-2 py-1 text-xs"
              style={inputStyle}
            >
              <option value="site-002">site-002 — Sandton City</option>
              <option value="site-001">site-001 — FNB Fairlands</option>
            </select>
          </div>
          <div>
            <label className="block text-xs mb-1" style={textSecondary}>Safety Class</label>
            <select
              value={safetyFilter}
              onChange={(e) => setSafetyFilter(e.target.value as SafetyClass | "")}
              className="rounded px-2 py-1 text-xs"
              style={inputStyle}
            >
              <option value="">All</option>
              {safetyClasses.map((cls) => (
                <option key={cls} value={cls}>{cls}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs mb-1" style={textSecondary}>Sort</label>
            <select
              value={sortByPriority ? "priority" : "default"}
              onChange={(e) => setSortByPriority(e.target.value === "priority")}
              className="rounded px-2 py-1 text-xs"
              style={inputStyle}
            >
              <option value="priority">By Priority</option>
              <option value="default">Default</option>
            </select>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          {loading ? (
            <div className="p-8 text-center text-sm" style={textSecondary}>
              Loading review queue...
            </div>
          ) : entries.length === 0 ? (
            <div className="p-8 text-center">
              <CheckCircle className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-green)" }} />
              <p className="text-sm" style={textSecondary}>
                No pending reviews{safetyFilter ? ` for safety class ${safetyFilter}` : ""}
              </p>
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={borderStyle}>
                  {["Point ID", "Equipment", "Tags", "Confidence", "Safety", "Priority", "Actions"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium" style={textSecondary}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-b hover:bg-white/5 transition-colors" style={borderStyle}>
                    <td className="px-3 py-2 font-mono" style={textPrimary}>{entry.point_id}</td>
                    <td className="px-3 py-2" style={textSecondary}>{entry.equipment_id}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {entry.semantic_tags.map((tag) => (
                          <span
                            key={tag}
                            className="px-1.5 py-0.5 rounded text-xs"
                            style={{ background: "rgba(99,102,241,0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(99,102,241,0.3)" }}
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium" style={confidenceBadgeStyle(entry.confidence_level)}>
                        {(entry.confidence_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium" style={safetyBadgeStyle(entry.safety_class)}>
                        {entry.safety_class}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className="px-1.5 py-0.5 rounded text-xs font-medium"
                        style={entry.priority <= 50 ? { color: "var(--color-sentinel-red)", background: "rgba(239,68,68,0.1)" } : textSecondary}
                      >
                        {entry.priority}
                      </span>
                      {!entry.validation_passed && (
                        <AlertTriangle
                          className="inline ml-1 h-3 w-3"
                          style={{ color: "var(--color-sentinel-amber)" }}
                          aria-label="Validation errors"
                        />
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleApprove(entry.id)}
                          className="flex items-center gap-0.5 px-2 py-1 rounded transition-colors hover:brightness-110"
                          style={{ background: "rgba(34,197,94,0.1)", color: "var(--color-sentinel-green)", border: "1px solid rgba(34,197,94,0.2)" }}
                        >
                          <CheckCircle className="h-3 w-3" />
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReject(entry.id)}
                          className="flex items-center gap-0.5 px-2 py-1 rounded transition-colors hover:brightness-110"
                          style={{ background: "rgba(239,68,68,0.1)", color: "var(--color-sentinel-red)", border: "1px solid rgba(239,68,68,0.2)" }}
                        >
                          <XCircle className="h-3 w-3" />
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Confidence level legend */}
        <div className="p-3 border-t flex flex-wrap gap-4" style={borderStyle}>
          <p className="text-xs" style={textSecondary}>Confidence:</p>
          {confidenceLevels.map((level) => (
            <span key={level} className="flex items-center gap-1">
              <span className="px-1.5 py-0.5 rounded text-xs font-medium" style={confidenceBadgeStyle(level)}>
                {level}
              </span>
              <span className="text-xs" style={textSecondary}>
                {level === "HIGH" ? ">= 70%" : level === "MEDIUM" ? "40–70%" : "< 40%"}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Approve Modal */}
      {approveModal.open && (
        <ModalPortal>
          <div className="glass-panel w-full max-w-md shadow-2xl" style={{ maxHeight: "calc(100vh - 2rem)" }}>
            <div className="flex items-center justify-between px-5 py-4 border-b" style={borderStyle}>
              <h3 className="font-semibold" style={textPrimary}>Approve Classification</h3>
              <button
                type="button"
                onClick={() => setApproveModal({ open: false, entryId: null, notes: "" })}
                className="p-1 rounded hover:bg-white/10 transition-colors"
                style={textSecondary}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 py-4 space-y-4">
              <p className="text-sm" style={textSecondary}>
                This classification will be approved and enabled for control decisions.
              </p>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={textSecondary}>
                  Review notes <span style={{ opacity: 0.6 }}>(optional)</span>
                </label>
                <textarea
                  value={approveModal.notes}
                  onChange={(e) => setApproveModal((s) => ({ ...s, notes: e.target.value }))}
                  placeholder="Add any notes about this approval..."
                  style={textareaStyle}
                />
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2" style={borderStyle}>
              <button
                type="button"
                onClick={() => setApproveModal({ open: false, entryId: null, notes: "" })}
                className="px-4 py-1.5 rounded text-sm transition-colors hover:bg-white/10"
                style={textSecondary}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitApprove}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110"
                style={{ background: "rgba(34,197,94,0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(34,197,94,0.3)" }}
              >
                <CheckCircle className="h-4 w-4" />
                Approve
              </button>
            </div>
          </div>
        </ModalPortal>
      )}

      {/* Reject Modal */}
      {rejectModal.open && (
        <ModalPortal>
          <div className="glass-panel w-full max-w-md shadow-2xl" style={{ maxHeight: "calc(100vh - 2rem)" }}>
            <div className="flex items-center justify-between px-5 py-4 border-b" style={borderStyle}>
              <h3 className="font-semibold" style={textPrimary}>Reject Classification</h3>
              <button
                type="button"
                onClick={() => setRejectModal({ open: false, entryId: null, reason: "", notes: "" })}
                className="p-1 rounded hover:bg-white/10 transition-colors"
                style={textSecondary}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 py-4 space-y-4">
              <p className="text-sm" style={textSecondary}>
                This classification will be rejected and excluded from control decisions.
              </p>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={textSecondary}>
                  Reason <span style={{ color: "var(--color-sentinel-red)" }}>*</span>
                </label>
                <input
                  type="text"
                  value={rejectModal.reason}
                  onChange={(e) => setRejectModal((s) => ({ ...s, reason: e.target.value }))}
                  placeholder="e.g. wrong tag, duplicate point, sensor offline..."
                  style={inputStyle}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={textSecondary}>
                  Additional notes <span style={{ opacity: 0.6 }}>(optional)</span>
                </label>
                <textarea
                  value={rejectModal.notes}
                  onChange={(e) => setRejectModal((s) => ({ ...s, notes: e.target.value }))}
                  placeholder="Any additional context..."
                  style={textareaStyle}
                />
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2" style={borderStyle}>
              <button
                type="button"
                onClick={() => setRejectModal({ open: false, entryId: null, reason: "", notes: "" })}
                className="px-4 py-1.5 rounded text-sm transition-colors hover:bg-white/10"
                style={textSecondary}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitReject}
                disabled={!rejectModal.reason.trim()}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: "rgba(239,68,68,0.15)", color: "var(--color-sentinel-red)", border: "1px solid rgba(239,68,68,0.3)" }}
              >
                <XCircle className="h-4 w-4" />
                Reject
              </button>
            </div>
          </div>
        </ModalPortal>
      )}

      {/* Bulk Approve Confirmation Modal */}
      {bulkModal.open && (
        <ModalPortal>
          <div className="glass-panel w-full max-w-sm shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b" style={borderStyle}>
              <h3 className="font-semibold" style={textPrimary}>Confirm Bulk Approval</h3>
              <button
                type="button"
                onClick={() => setBulkModal({ open: false, eligibleIds: [] })}
                className="p-1 rounded hover:bg-white/10 transition-colors"
                style={textSecondary}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 py-4">
              <p className="text-sm mb-3" style={textPrimary}>
                Approve{" "}
                <span className="font-semibold" style={{ color: "var(--color-sentinel-green)" }}>
                  {bulkModal.eligibleIds.length}
                </span>{" "}
                classifications?
              </p>
              <p className="text-xs" style={textSecondary}>
                Only entries with HIGH confidence (≥ 70%) and LOW safety class are included.
                These will be enabled for autonomous control decisions.
              </p>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2" style={borderStyle}>
              <button
                type="button"
                onClick={() => setBulkModal({ open: false, eligibleIds: [] })}
                className="px-4 py-1.5 rounded text-sm transition-colors hover:bg-white/10"
                style={textSecondary}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitBulkApprove}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110"
                style={{ background: "rgba(34,197,94,0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(34,197,94,0.3)" }}
              >
                <CheckCircle className="h-4 w-4" />
                Approve All
              </button>
            </div>
          </div>
        </ModalPortal>
      )}
    </>
  );
}
