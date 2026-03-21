/**
 * Review Queue Dashboard
 *
 * Phase 162: Semantic Control Foundation — Plan 05.
 * Human-in-the-loop review interface for semantic classification decisions.
 * Facility managers review, approve, reject, and override classifications.
 */

import { useState, useEffect, useCallback } from "react";
import { ClipboardCheck, AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { reviewQueueApi } from "../../lib/api/reviewQueue";
import type { ReviewQueueEntry, ReviewQueueStats } from "../../lib/api/reviewQueue";

interface ReviewQueueDashboardProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: (message: string) => void;
}

type SafetyClass = "HIGH" | "MEDIUM" | "LOW";
type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";

function safetyBadgeStyle(safetyClass: string): React.CSSProperties {
  if (safetyClass === "HIGH") {
    return { background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" };
  }
  if (safetyClass === "MEDIUM") {
    return { background: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245,158,11,0.3)" };
  }
  return { background: "rgba(34,197,94,0.15)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.3)" };
}

function confidenceBadgeStyle(confidenceLevel: string): React.CSSProperties {
  if (confidenceLevel === "HIGH") {
    return { background: "rgba(34,197,94,0.15)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.3)" };
  }
  if (confidenceLevel === "MEDIUM") {
    return { background: "rgba(245,158,11,0.15)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245,158,11,0.3)" };
  }
  return { background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" };
}

export function ReviewQueueDashboard({
  siteId = "S002",
  onError,
  onSuccess,
}: ReviewQueueDashboardProps) {
  const [entries, setEntries] = useState<ReviewQueueEntry[]>([]);
  const [stats, setStats] = useState<ReviewQueueStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedSite, setSelectedSite] = useState(siteId);
  const [safetyFilter, setSafetyFilter] = useState<SafetyClass | "">("");
  const [sortByPriority, setSortByPriority] = useState(true);

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

  const handleApprove = async (entryId: string) => {
    const notes = window.prompt("Review notes (optional):");
    if (notes === null) return; // user cancelled
    try {
      await reviewQueueApi.approve(entryId, notes || "");
      onSuccess?.("Classification approved.");
      await loadData();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Approval failed");
    }
  };

  const handleReject = async (entryId: string) => {
    const reason = window.prompt("Reason for rejection:");
    if (!reason) return;
    const notes = window.prompt("Additional review notes (optional):") ?? "";
    try {
      await reviewQueueApi.reject(entryId, reason, notes);
      onSuccess?.("Classification rejected.");
      await loadData();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Rejection failed");
    }
  };

  const handleBulkApprove = async () => {
    const eligible = entries.filter(
      (e) => e.confidence_score >= 0.7 && e.safety_class === "LOW",
    );
    if (eligible.length === 0) {
      onError?.("No eligible entries (HIGH confidence + LOW safety) found for bulk approval.");
      return;
    }
    const confirmed = window.confirm(
      `Approve ${eligible.length} high-confidence, low-safety classifications?`,
    );
    if (!confirmed) return;
    try {
      const result = await reviewQueueApi.bulkApprove(eligible.map((e) => e.id));
      onSuccess?.(result.message);
      await loadData();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Bulk approval failed");
    }
  };

  const textPrimary: React.CSSProperties = { color: "var(--color-sentinel-text-primary)" };
  const textSecondary: React.CSSProperties = { color: "var(--color-sentinel-text-secondary)" };
  const borderColor = { borderColor: "var(--color-sentinel-border)" };
  const inputStyle: React.CSSProperties = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  const confidenceLevels: ConfidenceLevel[] = ["HIGH", "MEDIUM", "LOW"];
  const safetyClasses: SafetyClass[] = ["HIGH", "MEDIUM", "LOW"];

  return (
    <div className="glass-panel overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b" style={borderColor}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: "rgba(99,102,241,0.15)", color: "#818cf8" }}
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
            style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.3)" }}
          >
            <CheckCircle className="h-3 w-3" />
            Bulk Approve Safe
          </button>
        </div>
      </div>

      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b" style={borderColor}>
          <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <p className="text-xs mb-1" style={textSecondary}>
              Total Pending
            </p>
            <p className="text-2xl font-bold" style={textPrimary}>
              {stats.total_pending}
            </p>
          </div>
          <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <p className="text-xs mb-1" style={textSecondary}>
              High Priority
            </p>
            <p className="text-2xl font-bold" style={{ color: "#ef4444" }}>
              {stats.high_priority_count}
            </p>
          </div>
          <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <p className="text-xs mb-1" style={textSecondary}>
              Avg Age (hrs)
            </p>
            <p className="text-2xl font-bold" style={textPrimary}>
              {stats.avg_age_hours.toFixed(1)}
            </p>
          </div>
          <div className="rounded p-3" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
            <p className="text-xs mb-2" style={textSecondary}>
              By Safety Class
            </p>
            <div className="flex flex-wrap gap-1">
              {safetyClasses.map((cls) => (
                <span
                  key={cls}
                  className="px-1.5 py-0.5 rounded text-xs font-medium"
                  style={safetyBadgeStyle(cls)}
                >
                  {cls}: {stats.by_safety_class[cls] ?? 0}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 p-4 border-b" style={borderColor}>
        <div>
          <label className="block text-xs mb-1" style={textSecondary}>
            Site
          </label>
          <select
            value={selectedSite}
            onChange={(e) => setSelectedSite(e.target.value)}
            className="rounded px-2 py-1 text-xs"
            style={inputStyle}
          >
            <option value="S002">S002 — Fairlands</option>
            <option value="S001">S001 — Site 1</option>
          </select>
        </div>
        <div>
          <label className="block text-xs mb-1" style={textSecondary}>
            Safety Class
          </label>
          <select
            value={safetyFilter}
            onChange={(e) => setSafetyFilter(e.target.value as SafetyClass | "")}
            className="rounded px-2 py-1 text-xs"
            style={inputStyle}
          >
            <option value="">All</option>
            {safetyClasses.map((cls) => (
              <option key={cls} value={cls}>
                {cls}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs mb-1" style={textSecondary}>
            Sort
          </label>
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
            <CheckCircle className="h-8 w-8 mx-auto mb-2" style={{ color: "#22c55e" }} />
            <p className="text-sm" style={textSecondary}>
              No pending reviews{safetyFilter ? ` for safety class ${safetyFilter}` : ""}
            </p>
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b" style={borderColor}>
                {["Point ID", "Equipment", "Tags", "Confidence", "Safety", "Priority", "Actions"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-3 py-2 text-left font-medium"
                      style={textSecondary}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr
                  key={entry.id}
                  className="border-b hover:bg-white/5 transition-colors"
                  style={borderColor}
                >
                  <td className="px-3 py-2 font-mono" style={textPrimary}>
                    {entry.point_id}
                  </td>
                  <td className="px-3 py-2" style={textSecondary}>
                    {entry.equipment_id}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {entry.semantic_tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-1.5 py-0.5 rounded text-xs"
                          style={{
                            background: "rgba(99,102,241,0.15)",
                            color: "#818cf8",
                            border: "1px solid rgba(99,102,241,0.3)",
                          }}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className="px-1.5 py-0.5 rounded text-xs font-medium"
                      style={confidenceBadgeStyle(entry.confidence_level)}
                    >
                      {(entry.confidence_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className="px-1.5 py-0.5 rounded text-xs font-medium"
                      style={safetyBadgeStyle(entry.safety_class)}
                    >
                      {entry.safety_class}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className="px-1.5 py-0.5 rounded text-xs font-medium"
                      style={
                        entry.priority <= 50
                          ? { color: "#ef4444", background: "rgba(239,68,68,0.1)" }
                          : textSecondary
                      }
                    >
                      {entry.priority}
                    </span>
                    {!entry.validation_passed && (
                      <AlertTriangle
                        className="inline ml-1 h-3 w-3"
                        style={{ color: "var(--color-sentinel-amber)" }}
                        title="Validation errors"
                      />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => handleApprove(entry.id)}
                        className="flex items-center gap-0.5 px-2 py-1 rounded transition-colors hover:brightness-110"
                        style={{
                          background: "rgba(34,197,94,0.1)",
                          color: "#22c55e",
                          border: "1px solid rgba(34,197,94,0.2)",
                        }}
                      >
                        <CheckCircle className="h-3 w-3" />
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReject(entry.id)}
                        className="flex items-center gap-0.5 px-2 py-1 rounded transition-colors hover:brightness-110"
                        style={{
                          background: "rgba(239,68,68,0.1)",
                          color: "#ef4444",
                          border: "1px solid rgba(239,68,68,0.2)",
                        }}
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
      <div className="p-3 border-t flex flex-wrap gap-4" style={borderColor}>
        <p className="text-xs" style={textSecondary}>
          Confidence:
        </p>
        {confidenceLevels.map((level) => (
          <span key={level} className="flex items-center gap-1">
            <span
              className="px-1.5 py-0.5 rounded text-xs font-medium"
              style={confidenceBadgeStyle(level)}
            >
              {level}
            </span>
            <span className="text-xs" style={textSecondary}>
              {level === "HIGH" ? ">= 70%" : level === "MEDIUM" ? "40–70%" : "< 40%"}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
