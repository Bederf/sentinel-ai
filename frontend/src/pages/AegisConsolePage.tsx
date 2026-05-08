import { useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clock3, RefreshCw, Shield, List } from "lucide-react";
import { aegisApi, type AegisDashboardFilters, type AegisDashboardResponse, type AegisDecision } from "../lib/api/aegis";
import { formatDateTime } from "../lib/timeFormat";
import { PageLoading } from "../components/PageLoading";
import { Panel } from "../components/Panel";
import { ModuleContext } from "../contexts/moduleContextStore";
import { Filter } from "lucide-react";

interface AegisConsolePageProps {
  siteId?: string;
}

function asString(value: unknown, fallback: string = "-"): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return fallback;
}

function getFactors(decision: AegisDecision): Record<string, unknown> {
  return decision.contributing_factors ?? {};
}

function getPendingAgeMinutes(createdAt: string): number {
  const created = new Date(createdAt).getTime();
  const now = Date.now();
  return Math.max(0, Math.floor((now - created) / 60000));
}

function getApprovalOutcome(decision: AegisDecision): string {
  const cf = getFactors(decision);
  const fromFactors = cf.approval_outcome;
  if (typeof fromFactors === "string" && fromFactors) return fromFactors;
  const raw = (decision as unknown as { approval_outcome?: unknown }).approval_outcome;
  return asString(raw, "pending");
}

function getWriteStatus(decision: AegisDecision): string {
  const cf = getFactors(decision);
  return asString(decision.write_status ?? cf.execution_mode, "unknown");
}

export function AegisConsolePage({ siteId: propSiteId }: AegisConsolePageProps) {
  const moduleContext = useContext(ModuleContext);
  const siteId = propSiteId || moduleContext?.siteId || '';
  const [snapshot, setSnapshot] = useState<AegisDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<AegisDecision | null>(null);

  const [filters, setFilters] = useState<AegisDashboardFilters>({
    approval_outcome: "",
    execution_mode: "",
    dispatch_action_type: "",
    write_status: "",
  });

  const loadDashboard = useCallback(
    async (isRefresh: boolean = false) => {
      try {
        if (isRefresh) setRefreshing(true);
        else setLoading(true);

        const data = await aegisApi.getDashboard(siteId, filters);
        setSnapshot(data);
        setLastRefreshedAt(new Date().toISOString());
        setError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to load AEGIS dashboard";
        setError(message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [siteId, filters],
  );

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    const interval = setInterval(() => {
      void loadDashboard(true);
    }, 30000);
    return () => clearInterval(interval);
  }, [loadDashboard]);

  const pendingOver30m = useMemo(() => {
    if (!snapshot) return 0;
    return snapshot.pending_proposals.filter((decision) => getPendingAgeMinutes(decision.created_at) > 30).length;
  }, [snapshot]);

  const inferredTripwires = useMemo(() => {
    if (!snapshot) return { gateFailSignals: 0, repeatedHashSignals: 0, oldestPendingMinutes: 0 };

    const gateFailSignals = snapshot.activity.filter((decision) => {
      const cf = getFactors(decision);
      const status = asString(cf.quality_gate_status, "").toLowerCase();
      const finalStatus = asString(cf.quality_gate_status_final, "").toLowerCase();
      return status === "fail" || finalStatus === "fail";
    }).length;

    const hashCounts: Record<string, number> = {};
    for (const decision of snapshot.pending_proposals) {
      const hash = asString(getFactors(decision).command_hash, "");
      if (!hash) continue;
      hashCounts[hash] = (hashCounts[hash] || 0) + 1;
    }

    const repeatedHashSignals = Object.values(hashCounts).filter((count) => count >= 3).length;
    const oldestPendingMinutes = snapshot.pending_proposals.length
      ? Math.max(...snapshot.pending_proposals.map((decision) => getPendingAgeMinutes(decision.created_at)))
      : 0;

    return { gateFailSignals, repeatedHashSignals, oldestPendingMinutes };
  }, [snapshot]);

  const readiness = useMemo(() => {
    if (!snapshot) {
      return {
        illegalStates: 0,
        auditMissing: 0,
        blocker: false,
      };
    }

    const illegalStates = snapshot.activity.filter((decision) => {
      const writeStatus = getWriteStatus(decision).toLowerCase();
      const decisionType = asString(decision.decision_type, "").toLowerCase();
      const cf = getFactors(decision);
      const covVerified = cf.cov_verified === true;
      return writeStatus === "success" || writeStatus === "failed" || decisionType.includes("executed") || covVerified;
    }).length;

    const requiredFields = [
      "proposal_id",
      "command_hash",
      "approval_outcome",
      "quality_gate_status",
      "block_reason_code",
    ];

    const auditMissing = snapshot.activity.filter((decision) => {
      const cf = getFactors(decision);
      return requiredFields.some((field) => !asString(cf[field], ""));
    }).length;

    const blocker = inferredTripwires.oldestPendingMinutes > 1440 || illegalStates > 0 || auditMissing > 0;

    return { illegalStates, auditMissing, blocker };
  }, [snapshot, inferredTripwires]);

  const handleInspectDecision = async (decisionId: string) => {
    try {
      const fullDecision = await aegisApi.getDecision(decisionId);
      setSelectedDecision(fullDecision);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch decision details";
      setError(message);
    }
  };

  const kpiCards = snapshot
    ? [
        { label: "Proposals (24h)", value: snapshot.kpis.proposals_24h, accent: "var(--color-sentinel-blue)" },
        { label: "Approved (24h)", value: snapshot.kpis.approved_24h, accent: "var(--color-sentinel-green)" },
        { label: "Rejected (24h)", value: snapshot.kpis.rejected_24h, accent: "var(--color-sentinel-red)" },
        { label: "Blocked (24h)", value: snapshot.kpis.blocked_24h, accent: "var(--color-sentinel-amber)" },
        { label: "Avg Response (s)", value: snapshot.kpis.avg_response_time_s ?? "N/A", accent: "var(--color-sentinel-text-primary)" },
        { label: "Pending >30m", value: pendingOver30m, accent: pendingOver30m > 0 ? "var(--color-sentinel-red)" : "var(--color-sentinel-green)" },
      ]
    : [];

  if (loading) {
    return <PageLoading message="Loading AEGIS console..." />;
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="mx-auto max-w-[1600px] space-y-6">
        <div
          className="rounded-lg p-4 md:p-5"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                AEGIS Ops Console
              </h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Site: {siteId} • Period: {snapshot?.period || "last_24h"} • Last refresh: {lastRefreshedAt ? formatDateTime(lastRefreshedAt) : "never"}
              </p>
            </div>
            <button
              onClick={() => void loadDashboard(true)}
              className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>

          {error && (
            <div
              className="mt-4 rounded-lg px-3 py-2 text-sm"
              style={{
                background: "rgba(220, 38, 38, 0.15)",
                border: "1px solid rgba(220, 38, 38, 0.3)",
                color: "var(--color-sentinel-red)",
              }}
            >
              {error}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          {kpiCards.map((card) => (
            <div
              key={card.label}
              className="rounded-lg p-3"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                border: "1px solid var(--color-sentinel-border)",
              }}
            >
              <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {card.label}
              </div>
              <div
              className="mt-1 text-2xl font-semibold"
              style={{ color: card.accent, fontVariantNumeric: "tabular-nums" }}
            >
              {card.value}
            </div>
            </div>
          ))}
        </div>

        <Panel
          header={{
            icon: <Filter className="h-4 w-4" />,
            title: "Filters",
            accentColor: "var(--color-sentinel-blue)",
          }}
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <select
              value={filters.approval_outcome || ""}
              onChange={(e) => setFilters((prev) => ({ ...prev, approval_outcome: e.target.value }))}
              className="rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
            >
              <option value="">Approval: all</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
            <select
              value={filters.execution_mode || ""}
              onChange={(e) => setFilters((prev) => ({ ...prev, execution_mode: e.target.value }))}
              className="rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
            >
              <option value="">Execution mode: all</option>
              <option value="blocked">Blocked</option>
              <option value="shadow">Shadow</option>
              <option value="live">Live</option>
            </select>
            <select
              value={filters.dispatch_action_type || ""}
              onChange={(e) => setFilters((prev) => ({ ...prev, dispatch_action_type: e.target.value }))}
              className="rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
            >
              <option value="">Dispatch action: all</option>
              <option value="charge">Charge</option>
              <option value="discharge">Discharge</option>
              <option value="idle">Idle</option>
            </select>
            <select
              value={filters.write_status || ""}
              onChange={(e) => setFilters((prev) => ({ ...prev, write_status: e.target.value }))}
              className="rounded-lg px-3 py-2 text-sm"
              style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}
            >
              <option value="">Write status: all</option>
              <option value="blocked">Blocked</option>
              <option value="success">Success</option>
              <option value="skipped">Skipped</option>
            </select>
          </div>
        </Panel>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="xl:col-span-2">
          <Panel
            header={{
              icon: <AlertTriangle className="h-4 w-4" />,
              title: "Pending proposals",
              accentColor: "var(--color-sentinel-amber)",
            }}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    <th className="px-2 py-2 text-left">Created</th>
                    <th className="px-2 py-2 text-left">Equipment</th>
                    <th className="px-2 py-2 text-left">Action</th>
                    <th className="px-2 py-2 text-left">SOC Target</th>
                    <th className="px-2 py-2 text-left">Gate</th>
                    <th className="px-2 py-2 text-left">Age</th>
                    <th className="px-2 py-2 text-left">Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {(snapshot?.pending_proposals || []).slice(0, 200).map((decision) => {
                    const cf = getFactors(decision);
                    return (
                      <tr key={decision.id} style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                        <td className="px-2 py-2">{formatDateTime(decision.created_at)}</td>
                        <td className="px-2 py-2">{asString(decision.equipment_code)}</td>
                        <td className="px-2 py-2">{asString(cf.dispatch_action_type)}</td>
                        <td className="px-2 py-2">{asString(cf.target_soc_pct, "N/A")}</td>
                        <td className="px-2 py-2">{asString(cf.quality_gate_status)}</td>
                        <td className="px-2 py-2">{getPendingAgeMinutes(decision.created_at)}m</td>
                        <td className="px-2 py-2">
                          <button
                            onClick={() => void handleInspectDecision(decision.id)}
                            className="rounded-lg px-2 py-1 text-xs"
                            style={{
                              background: "var(--color-sentinel-bg-secondary)",
                              border: "1px solid var(--color-sentinel-border)",
                              color: "var(--color-sentinel-text-primary)",
                            }}
                          >
                            Open
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          </div>

          <div className="space-y-6">
            <Panel
              header={{
                icon: <AlertTriangle className="h-4 w-4" />,
                title: "Tripwire signals",
                accentColor: "var(--color-sentinel-amber)",
              }}
            >
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Gate-fail signals</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{inferredTripwires.gateFailSignals}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Repeated-hash signals</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{inferredTripwires.repeatedHashSignals}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Oldest pending</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{inferredTripwires.oldestPendingMinutes} min</span>
                </div>
              </div>
              <p className="mt-3 text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                Signals are inferred from decisions. Canonical tripwire aging remains in decision logs.
              </p>
            </Panel>

            <Panel
              header={{
                icon: <Shield className="h-4 w-4" />,
                title: "Readiness",
                accentColor: "var(--color-sentinel-blue)",
              }}
            >
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Illegal states</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{readiness.illegalStates}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Audit gaps</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{readiness.auditMissing}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Phase 1 blocker</span>
                  <span style={{ color: readiness.blocker ? "var(--color-sentinel-red)" : "var(--color-sentinel-green)" }}>
                    {readiness.blocker ? "Yes" : "No"}
                  </span>
                </div>
              </div>
            </Panel>
          </div>
        </div>

        <Panel
          header={{
            icon: <List className="h-4 w-4" />,
            title: "Activity timeline",
            accentColor: "var(--color-sentinel-blue)",
          }}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <th className="px-2 py-2 text-left">Time</th>
                  <th className="px-2 py-2 text-left">Decision</th>
                  <th className="px-2 py-2 text-left">Equipment</th>
                  <th className="px-2 py-2 text-left">Outcome</th>
                  <th className="px-2 py-2 text-left">Write Status</th>
                  <th className="px-2 py-2 text-left">Action</th>
                </tr>
              </thead>
              <tbody>
                {(snapshot?.activity || []).slice(0, 400).map((decision) => {
                  const cf = getFactors(decision);
                  return (
                    <tr key={decision.id} style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                      <td className="px-2 py-2">{formatDateTime(decision.created_at)}</td>
                      <td className="px-2 py-2">{asString(decision.decision_type)}</td>
                      <td className="px-2 py-2">{asString(decision.equipment_code)}</td>
                      <td className="px-2 py-2">{getApprovalOutcome(decision)}</td>
                      <td className="px-2 py-2">{getWriteStatus(decision)}</td>
                      <td className="px-2 py-2">{asString(cf.dispatch_action_type)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        {selectedDecision && (
          <Panel
            header={{
              title: `Decision detail: ${selectedDecision.id}`,
              actions: (
                <button
                  className="rounded-lg px-2 py-1 text-xs"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                  onClick={() => setSelectedDecision(null)}
                >
                  Close
                </button>
              ),
              accentColor: "var(--color-sentinel-blue)",
            }}
          >
            <pre
              className="max-h-[420px] overflow-auto rounded-lg p-3 text-xs"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              {JSON.stringify(selectedDecision, null, 2)}
            </pre>
          </Panel>
        )}

        <div className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          <Clock3 className="mr-1 inline h-3 w-3" />
          Auto-refresh every 30 seconds. This page is read-only and does not execute control actions.
        </div>
      </div>
    </div>
  );
}

export default AegisConsolePage;
