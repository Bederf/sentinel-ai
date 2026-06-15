/**
 * CompliancePage — OHS, Fire, Electrical, Legionella, Lift Safety.
 *
 * Overview tab: ScoreRing + KPI cards + domain status + recent audits.
 * Domain tabs: delegate to existing sub-panel components (migrated separately).
 */

import { useState, useContext } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  Clock,
  ClipboardList,
  Flame,
  Droplets,
  Zap,
  ArrowUpDown,
  Database,
} from "lucide-react";
import { PageLoading } from "../components/PageLoading";
import { Panel } from "../components/Panel";
import { TabBar } from "../components/TabBar";
import { ScoreRing } from "../components/ScoreRing";
import { KPICard } from "../components/KPICard";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import type { StatusKey } from "../components/StatusBadge";
import {
  useComplianceStatus,
  useComplianceAudits,
  useRetentionStatus,
  useRetentionHistory,
  type AuditStatus,
} from "../lib/api/compliance";
import { OHSPanel } from "../components/compliance/OHSPanel";
import { FireEquipmentPanel } from "../components/compliance/FireEquipmentPanel";
import { EmergencyLightPanel } from "../components/compliance/EmergencyLightPanel";
import { LegionellaPanel } from "../components/compliance/LegionellaPanel";
import { ElectricalCompliancePanel } from "../components/compliance/ElectricalCompliancePanel";
import { LiftInspectionPanel } from "../components/compliance/LiftInspectionPanel";
import { ModuleContext } from "../contexts/moduleContextStore";

const TABS = [
  { id: "overview",   label: "Overview" },
  { id: "ohs",        label: "OHS" },
  { id: "fire",       label: "Fire Safety" },
  { id: "emergency",  label: "Emergency Lights" },
  { id: "legionella", label: "Legionella" },
  { id: "electrical", label: "Electrical" },
  { id: "lift",       label: "Lift Safety" },
];

// Maps API domain status values → StatusKey, handling call-site aliases
function domainStatusKey(status?: string): StatusKey {
  if (!status) return "pending";
  if (status === "expiring_soon") return "expiring";
  if (status === "high_risk") return "high_risk";
  return status as StatusKey;
}

// Maps AuditStatus → StatusKey using closest semantic match
function auditStatusKey(status: AuditStatus): StatusKey {
  switch (status) {
    case "draft":               return "draft";
    case "submitted":           return "pending";
    case "approved":            return "compliant";
    case "remediation_pending": return "expiring";
    case "closed":              return "completed";
    default:                    return "pending";
  }
}

function auditStatusLabel(status: AuditStatus): string {
  switch (status) {
    case "draft":               return "Draft";
    case "submitted":           return "Submitted";
    case "approved":            return "Approved";
    case "remediation_pending": return "Remediation";
    case "closed":              return "Closed";
    default:                    return status;
  }
}

export function CompliancePage() {
  const [activeTab, setActiveTab] = useState("overview");
  const { siteId: contextSiteId } = useContext(ModuleContext);
  // site-001 is blocked from frontend polling — fall back to site-002 if context is invalid
  const siteCode = contextSiteId && contextSiteId !== "site-001" ? contextSiteId : "site-002";

  const { data: status, isLoading } = useComplianceStatus(siteCode);
  const { data: auditsData } = useComplianceAudits(siteCode);
  const { data: retentionStatus } = useRetentionStatus();
  const { data: retentionHistory } = useRetentionHistory(5);

  const score = status?.compliance_score_percent ?? 0;
  const criticalCount = status?.critical_issues_count ?? 0;
  const expiringCount = status?.items_expiring_30days ?? 0;
  const overdueCount = status?.overdue_inspections ?? 0;

  const domainRows: { label: string; icon: React.ReactNode; statusVal?: string }[] = [
    { label: "OHS Compliance",  icon: <ShieldCheck className="h-4 w-4" />, statusVal: status?.summary?.ohs_status },
    { label: "Fire Safety",     icon: <Flame className="h-4 w-4" />,       statusVal: status?.summary?.fire_status },
    { label: "Electrical",      icon: <Zap className="h-4 w-4" />,         statusVal: status?.summary?.electrical_status },
    { label: "Legionella",      icon: <Droplets className="h-4 w-4" />,    statusVal: status?.summary?.legionella_status },
    { label: "Lift Safety",     icon: <ArrowUpDown className="h-4 w-4" />, statusVal: status?.summary?.lift_status },
  ];

  return (
    <div
      className="h-full overflow-y-auto"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {isLoading ? (
        <PageLoading message="Loading compliance data…" />
      ) : (
      <div className="space-y-6 p-4 md:p-6">

        <TabBar
          tabs={TABS}
          active={activeTab}
          onChange={setActiveTab}
          accentColor="var(--color-sentinel-blue)"
        />

        {/* Overview tab */}
        {activeTab === "overview" && (
          <>
            {/* Score + KPI row */}
            <div className="flex flex-col gap-4 md:flex-row md:items-start">
              {/* ScoreRing */}
              <div
                className="flex flex-col items-center gap-2 rounded-lg p-4 flex-shrink-0"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  border: "1px solid var(--color-sentinel-border)",
                  minWidth: 160,
                }}
              >
                <ScoreRing
                  score={score}
                  size={120}
                  strokeWidth={10}
                  color={
                    score >= 80
                      ? "var(--color-sentinel-green)"
                      : score >= 60
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-red)"
                  }
                />
                <span
                  className="text-xs font-medium"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Compliance Score
                </span>
              </div>

              {/* KPI cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 flex-1">
                <KPICard
                  title="Critical Issues"
                  value={criticalCount}
                  icon={<AlertTriangle className="h-5 w-5" />}
                  accentColor="red"
                  delta={criticalCount > 0 ? criticalCount : undefined}
                  deltaText="open"
                />
                <KPICard
                  title="Expiring (30 days)"
                  value={expiringCount}
                  icon={<Clock className="h-5 w-5" />}
                  accentColor="orange"
                />
                <KPICard
                  title="Overdue"
                  value={overdueCount}
                  icon={<AlertTriangle className="h-5 w-5" />}
                  accentColor={overdueCount > 0 ? "red" : "green"}
                />
              </div>
            </div>

            {/* Domain status summary */}
            <Panel
              header={{
                icon: <ShieldCheck className="h-4 w-4" />,
                title: "Domain Status",
                accentColor: "var(--color-sentinel-blue)",
              }}
            >
              <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                {domainRows.map(({ label, icon, statusVal }) => (
                  <div
                    key={label}
                    className="flex items-center justify-between py-2 px-3 rounded"
                    style={{ background: "var(--color-sentinel-bg-secondary)" }}
                  >
                    <div className="flex items-center gap-2">
                      <span style={{ color: "var(--color-sentinel-text-disabled)" }}>{icon}</span>
                      <span
                        className="text-sm"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {label}
                      </span>
                    </div>
                    <StatusBadge
                      status={domainStatusKey(statusVal)}
                      label={
                        statusVal
                          ? statusVal.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
                          : "Pending"
                      }
                    />
                  </div>
                ))}
              </div>
            </Panel>

            {/* Recent audits */}
            <Panel
              header={{
                icon: <ClipboardList className="h-4 w-4" />,
                title: "Recent Audits",
                accentColor: "var(--color-sentinel-blue)",
              }}
            >
              {!auditsData?.audits?.length ? (
                <div className="p-6">
                  <EmptyState
                    icon={ClipboardList}
                    title="No audits recorded"
                    subtext="Compliance audits will appear here once scheduled."
                  />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr
                        style={{
                          borderBottom: "1px solid var(--color-sentinel-border)",
                          background: "var(--color-sentinel-bg-secondary)",
                        }}
                      >
                        {["Type", "Status", "Date"].map((h) => (
                          <th
                            key={h}
                            className="px-4 py-2 text-left text-xs font-medium"
                            style={{ color: "var(--color-sentinel-text-secondary)" }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {auditsData.audits.slice(0, 8).map((audit) => (
                        <tr
                          key={audit.id}
                          style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
                        >
                          <td
                            className="px-4 py-2.5 text-sm"
                            style={{ color: "var(--color-sentinel-text-primary)" }}
                          >
                            {audit.compliance_type}
                          </td>
                          <td className="px-4 py-2.5">
                            <StatusBadge
                              status={auditStatusKey(audit.status)}
                              label={auditStatusLabel(audit.status)}
                            />
                          </td>
                          <td
                            className="px-4 py-2.5 text-sm"
                            style={{ color: "var(--color-sentinel-text-secondary)" }}
                          >
                            {new Date(audit.created_at).toLocaleDateString("en-ZA")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            {/* POPIA Data Retention */}
            <Panel
              header={{
                icon: <Database className="h-4 w-4" />,
                title: "POPIA Data Retention",
                accentColor: "var(--color-sentinel-blue)",
              }}
            >
              <div className="p-4 space-y-4">
                {retentionStatus?.categories ? (
                  <>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {retentionStatus.categories
                        .reduce<Array<{ tier: string; label: string; count: number; days: number }>>(
                          (acc, cat) => {
                            const existing = acc.find((a) => a.tier === cat.tier);
                            if (existing) {
                              existing.count += cat.overdue_count;
                            } else {
                              const labels: Record<string, string> = {
                                ML_TRAINING: "ML Training (7d)",
                                SNAPSHOT: "Snapshots (30d)",
                                AUDIT_TRAIL: "Audit Trail (5y)",
                              };
                              acc.push({
                                tier: cat.tier,
                                label: labels[cat.tier] ?? cat.tier,
                                count: cat.overdue_count,
                                days: cat.retention_days,
                              });
                            }
                            return acc;
                          },
                          []
                        )
                        .map(({ tier, label, count, days }) => (
                          <div
                            key={tier}
                            className="flex items-center justify-between py-2 px-3 rounded"
                            style={{ background: "var(--color-sentinel-bg-secondary)" }}
                          >
                            <div className="flex flex-col">
                              <span
                                className="text-xs font-medium"
                                style={{ color: "var(--color-sentinel-text-primary)" }}
                              >
                                {label}
                              </span>
                              <span
                                className="text-xs"
                                style={{ color: "var(--color-sentinel-text-secondary)" }}
                              >
                                {days} day retention
                              </span>
                            </div>
                            <span
                              className="text-sm font-medium"
                              style={{
                                color:
                                  count > 0
                                    ? "var(--color-sentinel-amber)"
                                    : "var(--color-sentinel-green)",
                              }}
                            >
                              {count.toLocaleString()}
                            </span>
                          </div>
                        ))}
                    </div>

                    {retentionHistory?.items && retentionHistory.items.length > 0 && (
                      <div>
                        <p
                          className="text-xs font-medium mb-2"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          Recent Enforcement Runs
                        </p>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs">
                            <thead>
                              <tr
                                style={{
                                  borderBottom: "1px solid var(--color-sentinel-border)",
                                  background: "var(--color-sentinel-bg-secondary)",
                                }}
                              >
                                {["Tier", "Reviewed", "Deleted", "Status", "Time"].map((h) => (
                                  <th
                                    key={h}
                                    className="px-3 py-1.5 text-left font-medium"
                                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                                  >
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {retentionHistory.items.slice(0, 5).map((log) => (
                                <tr
                                  key={log.id}
                                  style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
                                >
                                  <td
                                    className="px-3 py-1.5"
                                    style={{ color: "var(--color-sentinel-text-primary)" }}
                                  >
                                    {log.tier}
                                  </td>
                                  <td
                                    className="px-3 py-1.5"
                                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                                  >
                                    {log.rows_reviewed?.toLocaleString() ?? "—"}
                                  </td>
                                  <td
                                    className="px-3 py-1.5"
                                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                                  >
                                    {log.rows_deleted?.toLocaleString() ?? "—"}
                                  </td>
                                  <td className="px-3 py-1.5">
                                    <StatusBadge
                                      status={log.status === "success" ? "compliant" : "high_risk"}
                                      label={log.status}
                                    />
                                  </td>
                                  <td
                                    className="px-3 py-1.5"
                                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                                  >
                                    {new Date(log.execution_time).toLocaleDateString("en-ZA")}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <EmptyState
                    icon={Database}
                    title="Retention status unavailable"
                    subtext="POPIA retention service may be offline."
                  />
                )}
              </div>
            </Panel>
          </>
        )}

        {activeTab === "ohs"        && <OHSPanel siteCode={siteCode} />}
        {activeTab === "fire"       && <FireEquipmentPanel siteCode={siteCode} />}
        {activeTab === "emergency"  && <EmergencyLightPanel siteCode={siteCode} />}
        {activeTab === "legionella" && <LegionellaPanel siteCode={siteCode} />}
        {activeTab === "electrical" && <ElectricalCompliancePanel siteCode={siteCode} />}
        {activeTab === "lift"       && <LiftInspectionPanel siteCode={siteCode} />}
      </div>
      )}
    </div>
  );
}

export default CompliancePage;
