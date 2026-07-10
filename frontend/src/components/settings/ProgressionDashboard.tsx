/**
 * ProgressionDashboard — trust-ladder visibility widget.
 *
 * Phase D of the progression engine: shows site-level trust state,
 * per-class readiness scores, and gates for the next level.
 *
 * Fetches from GET /api/progression/trust/{siteId}
 */

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { AlertTriangle, Shield, TrendingUp, Clock, CheckCircle, XCircle, Activity } from "lucide-react";

interface ClassReadiness {
  class_name: string;
  current_trust_level: number;
  evidence_count: number;
  accuracy_pct_7d: number | null;
  accuracy_pct_30d: number | null;
  consecutive_successes: number;
  consecutive_failures: number;
  last_validation_at: string | null;
  last_demotion_at: string | null;
  demotion_reason: string | null;
}

interface GateStatus {
  required: number | boolean;
  current: number | boolean | null;
  pass: boolean;
}

interface TrustSummary {
  site_id: string;
  current_level: number;
  next_level: number;
  readiness_score: number;
  total_evidence_count: number;
  accuracy_pct_30d_weighted: number | null;
  class_count: number;
  gates_for_next_level: Record<string, GateStatus> | null;
  classes: ClassReadiness[];
  evaluated_at: string;
}

const LEVEL_LABELS: Record<number, string> = {
  1: "Advisory",
  2: "Supervised",
  3: "Autonomous",
};

const LEVEL_COLORS: Record<number, string> = {
  1: "#f59e0b",
  2: "#3b82f6",
  3: "#10b981",
};

function GateIcon({ pass }: { pass: boolean }) {
  return pass
    ? <CheckCircle size={16} className="text-green-400" />
    : <XCircle size={16} className="text-red-400" />;
}

/** Convert accuracy from 0-100 scale to 0-1 for display */
function accDisplay(val: number | null): string {
  if (val === null || val === undefined) return "—";
  return `${(val / 100).toFixed(1)}%`;
}

export function ProgressionDashboard({ siteId }: { siteId: string }) {
  const [data, setData] = useState<TrustSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overrideState, setOverrideState] = useState<{
    type: string;
    class_name: string;
    level: number;
    hold_until: string;
    reason: string;
  }>({ type: "hold_site", class_name: "", level: 1, hold_until: "", reason: "" });

  const fetchTrust = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/progression/trust/${siteId}`);
      setData(res.data as TrustSummary);
    } catch (err: any) {
      setError(err?.message || "Failed to fetch trust data");
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchTrust();
  }, [fetchTrust]);

  const handleOverride = async () => {
    try {
      const body: Record<string, any> = {
        override_type: overrideState.type,
        reason: overrideState.reason || "Operator override",
      };
      if (overrideState.type === "hold_site" && overrideState.hold_until) {
        body.hold_until = overrideState.hold_until;
      }
      if (overrideState.type === "override_class_level") {
        body.class_name = overrideState.class_name;
        body.override_level = overrideState.level;
      }
      await api.post(`/api/progression/override/${siteId}`, body);
      fetchTrust();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Override failed");
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800/60 rounded-lg border border-gray-700/60 p-6 animate-pulse">
        <div className="h-6 w-48 bg-gray-700 rounded mb-4" />
        <div className="h-4 w-96 bg-gray-700 rounded" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="bg-gray-800/60 rounded-lg border border-red-700/60 p-6">
        <div className="flex items-center gap-2 text-red-400 mb-2">
          <AlertTriangle size={18} />
          <span className="font-medium">Trust data unavailable</span>
        </div>
        <p className="text-gray-400 text-sm">{error}</p>
        <button onClick={fetchTrust} className="mt-3 text-sm text-blue-400 hover:text-blue-300 underline">
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-gray-800/60 rounded-lg border border-gray-700/60 p-6">
        <p className="text-gray-400 text-sm">No trust data available for {siteId}.</p>
        <p className="text-gray-500 text-xs mt-1">Recommendations must flow through validation before trust levels populate.</p>
      </div>
    );
  }

  const isMaxLevel = data.current_level >= 3;

  return (
    <div className="space-y-6">
      {/* ── Site-level trust card ── */}
      <div className="bg-gray-800/60 rounded-lg border border-gray-700/60 p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Shield size={20} className="text-blue-400" />
            <h3 className="text-base font-semibold text-gray-100">Site Trust Level</h3>
          </div>
          <span className="text-xs text-gray-500">
            Evaluated: {new Date(data.evaluated_at).toLocaleTimeString()}
          </span>
        </div>

        <div className="flex items-center gap-4 mb-4">
          <div
            className="text-2xl font-bold px-3 py-1.5 rounded-md"
            style={{ backgroundColor: `${LEVEL_COLORS[data.current_level]}22`, color: LEVEL_COLORS[data.current_level] }}
          >
            Level {data.current_level}: {LEVEL_LABELS[data.current_level]}
          </div>
          {!isMaxLevel && (
            <div className="flex items-center gap-1.5 text-sm text-gray-400">
              <TrendingUp size={16} className="text-green-400" />
              <span>
                Readiness: <span className="text-gray-100 font-medium">{(data.readiness_score * 100).toFixed(0)}%</span>
                {" → "}Level {data.next_level}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4 mb-2">
          <div>
            <span className="text-xs text-gray-500 block">Total Evidence</span>
            <span className="text-lg font-semibold text-gray-100">{data.total_evidence_count}</span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Accuracy (30d)</span>
            <span className="text-lg font-semibold text-gray-100">
              {data.accuracy_pct_30d_weighted != null ? `${(data.accuracy_pct_30d_weighted / 100).toFixed(1)}%` : "—"}
            </span>
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Classes Tracked</span>
            <span className="text-lg font-semibold text-gray-100">{data.class_count}</span>
          </div>
        </div>

        {/* Gates for next level */}
        {!isMaxLevel && data.gates_for_next_level && (
          <div className="mt-4 pt-4 border-t border-gray-700/60">
            <h4 className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
              Gates — Level {data.current_level} → Level {data.next_level}
            </h4>
            <div className="space-y-1.5">
              {Object.entries(data.gates_for_next_level).map(([gate, status]) => (
                <div key={gate} className="flex items-center gap-2 text-sm">
                  <GateIcon pass={status.pass} />
                  <span className="text-gray-400 capitalize">{gate.replace(/_/g, " ")}</span>
                  <span className="text-gray-500 ml-auto">
                    <span className={status.pass ? "text-green-400" : "text-red-400"}>
                      {String(status.current ?? "—")}
                    </span>
                    <span className="text-gray-600"> / {String(status.required)}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Per-class readiness table ── */}
      <div className="bg-gray-800/60 rounded-lg border border-gray-700/60 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-700/60">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-400" />
            <h3 className="text-sm font-semibold text-gray-100">Class Readiness</h3>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700/40">
                <th className="text-left px-4 py-2.5 text-gray-400 font-medium">Class</th>
                <th className="text-center px-3 py-2.5 text-gray-400 font-medium">Level</th>
                <th className="text-right px-3 py-2.5 text-gray-400 font-medium">Evidence</th>
                <th className="text-right px-3 py-2.5 text-gray-400 font-medium">Acc 7d</th>
                <th className="text-right px-3 py-2.5 text-gray-400 font-medium">Acc 30d</th>
                <th className="text-right px-3 py-2.5 text-gray-400 font-medium">Failures</th>
                <th className="text-right px-3 py-2.5 text-gray-400 font-medium">Last Demotion</th>
              </tr>
            </thead>
            <tbody>
              {data.classes.map((cls) => (
                <tr key={cls.class_name} className="border-b border-gray-700/20 hover:bg-gray-700/20">
                  <td className="px-4 py-2.5 text-gray-200 font-medium">{cls.class_name}</td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className="inline-block px-2 py-0.5 rounded text-xs font-bold"
                      style={{ backgroundColor: `${LEVEL_COLORS[cls.current_trust_level]}22`, color: LEVEL_COLORS[cls.current_trust_level] }}
                    >
                      {cls.current_trust_level}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-300">{cls.evidence_count}</td>
                  <td className="px-3 py-2.5 text-right text-gray-300">{accDisplay(cls.accuracy_pct_7d)}</td>
                  <td className="px-3 py-2.5 text-right text-gray-300">{accDisplay(cls.accuracy_pct_30d)}</td>
                  <td className="px-3 py-2.5 text-right">
                    <span className={cls.consecutive_failures >= 3 ? "text-red-400" : "text-gray-300"}>
                      {cls.consecutive_failures}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-400 text-xs">
                    {cls.last_demotion_at ? (
                      <span title={cls.demotion_reason || ""}>
                        {new Date(cls.last_demotion_at).toLocaleDateString()}
                        {cls.demotion_reason && " ⚠"}
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
              {data.classes.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500 text-sm">
                    No class readiness data yet. Recommendations must flow through validation first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Operator override panel ── */}
      <div className="bg-gray-800/60 rounded-lg border border-gray-700/60 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Clock size={16} className="text-amber-400" />
          <h3 className="text-sm font-semibold text-gray-100">Operator Override</h3>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Override Type</label>
            <select
              className="w-full bg-gray-700/60 border border-gray-600/60 rounded px-3 py-2 text-sm text-gray-200"
              value={overrideState.type}
              onChange={(e) => setOverrideState((s) => ({ ...s, type: e.target.value }))}
            >
              <option value="hold_site">Hold Site at Current Level</option>
              <option value="override_class_level">Override Class Level</option>
            </select>
          </div>

          {overrideState.type === "hold_site" && (
            <div>
              <label className="text-xs text-gray-400 block mb-1">Hold Until (YYYY-MM-DD)</label>
              <input
                type="date"
                className="w-full bg-gray-700/60 border border-gray-600/60 rounded px-3 py-2 text-sm text-gray-200"
                value={overrideState.hold_until}
                onChange={(e) => setOverrideState((s) => ({ ...s, hold_until: e.target.value }))}
              />
            </div>
          )}

          {overrideState.type === "override_class_level" && (
            <>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Class Name</label>
                <select
                  className="w-full bg-gray-700/60 border border-gray-600/60 rounded px-3 py-2 text-sm text-gray-200"
                  value={overrideState.class_name}
                  onChange={(e) => setOverrideState((s) => ({ ...s, class_name: e.target.value }))}
                >
                  <option value="">Select class...</option>
                  {data.classes.map((c) => (
                    <option key={c.class_name} value={c.class_name}>{c.class_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Override Level (0-3)</label>
                <select
                  className="w-full bg-gray-700/60 border border-gray-600/60 rounded px-3 py-2 text-sm text-gray-200"
                  value={overrideState.level}
                  onChange={(e) => setOverrideState((s) => ({ ...s, level: Number(e.target.value) }))}
                >
                  <option value={0}>Level 0 (Shadow)</option>
                  <option value={1}>Level 1 (Advisory)</option>
                  <option value={2}>Level 2 (Supervised)</option>
                  <option value={3}>Level 3 (Autonomous)</option>
                </select>
              </div>
            </>
          )}
        </div>

        <div className="mb-4">
          <label className="text-xs text-gray-400 block mb-1">Reason (optional)</label>
          <input
            type="text"
            className="w-full bg-gray-700/60 border border-gray-600/60 rounded px-3 py-2 text-sm text-gray-200"
            placeholder="Why is this override being applied?"
            value={overrideState.reason}
            onChange={(e) => setOverrideState((s) => ({ ...s, reason: e.target.value }))}
          />
        </div>

        <button
          onClick={handleOverride}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded font-medium transition-colors"
        >
          Apply Override
        </button>

        {error && (
          <p className="mt-2 text-xs text-red-400">{error}</p>
        )}
      </div>
    </div>
  );
}
