import { useState, useEffect, useCallback } from "react";
import { Activity, ExternalLink, Archive, Download, ShieldCheck, CheckCircle2, AlertTriangle } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface BackupStatus {
  state: "idle" | "running";
  last_backup: string | null;
  last_backup_age_hours: number | null;
  file_count: number;
  total_size_mb: number;
  last_result: string | null;
}

interface DrStatus {
  status: "healthy" | "degraded" | "critical";
  score: number;
  local_restore_target: {
    last_result: string | null;
    last_restored_at: string | null;
    restore_age_hours: number | null;
    freshness_max_hours: number;
    table_count: number | null;
    critical_row_counts?: Record<string, number>;
    missing_critical_tables?: string[];
    empty_critical_tables?: string[];
    database_size_mb: number | null;
  };
  rpo: {
    local_restore_exposure_label: string;
    remote_wal_exposure_label: string;
  };
  rto: {
    last_database_layer_label: string;
  };
}

interface PhaseReadinessGate {
  gate: string;
  passed: boolean;
  value?: number | string | boolean | null;
  threshold?: number | null;
}

interface PhaseReadinessSite {
  site_id: string;
  site_name: string;
  current_phase: string;
  target_phase: string | null;
  eligible: boolean;
  gates_passed: number;
  gates_total: number;
  gates: PhaseReadinessGate[];
}

interface PhaseReadinessResponse {
  sites: PhaseReadinessSite[];
}

interface SiteProgressGate {
  name: string;
  passed: boolean;
  detail: string;
  action: string | null;
}

interface SiteProgressStage {
  stage: string;
  status: "completed" | "in_progress" | "blocked" | "not_reached";
  gates: SiteProgressGate[];
}

interface SiteProgressResponse {
  site_id: string;
  pls: SiteProgressStage;
  onboarding: SiteProgressStage;
  phase_promotion: SiteProgressStage;
  integrity: SiteProgressStage;
  next_actions: string[];
}

interface SystemHealthDashboardProps {
  siteId?: string;
  onError?: (error: string) => void;
  onNavigate?: (view: import("../../lib/navigation").View) => void;
}

export function SystemHealthDashboard({ siteId, onError, onNavigate }: SystemHealthDashboardProps) {
  const [backup, setBackup] = useState<BackupStatus | null>(null);
  const [drStatus, setDrStatus] = useState<DrStatus | null>(null);
  const [phaseReadiness, setPhaseReadiness] = useState<PhaseReadinessResponse | null>(null);
  const [siteProgress, setSiteProgress] = useState<Record<string, SiteProgressResponse>>({});
  const [backupTriggering, setBackupTriggering] = useState(false);

  const fetchBackupStatus = useCallback(async () => {
    try {
      const res = await authorizedFetch("/api/system/backup-status");
      if (res.ok) setBackup(await res.json());
      const dr = await authorizedFetch("/api/system/dr-status");
      if (dr.ok) setDrStatus(await dr.json());
      const phase = await authorizedFetch(`/api/system/phase-readiness${siteId ? `?site_id=${siteId}` : ""}`);
      if (phase.ok) setPhaseReadiness(await phase.json());

      // ── Fetch progress for each site ──────────────────────
      const progressMap: Record<string, SiteProgressResponse> = {};
      const siteIds = siteId ? [siteId] : ["site-001", "site-002", "site-004", "site-005"];
      for (const sid of siteIds) {
        const res = await authorizedFetch(`/api/system/sites/${sid}/progress`);
        if (res.ok) {
          const data: SiteProgressResponse = await res.json();
          progressMap[sid] = data;
        }
      }
      if (Object.keys(progressMap).length > 0) setSiteProgress(progressMap);
    } catch { /* ignore */ }
  }, [siteId]);

  const handleTriggerBackup = async () => {
    setBackupTriggering(true);
    try {
      const res = await authorizedFetch("/api/system/backup/trigger", { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        onError?.(err.detail || "Failed to trigger backup");
        return;
      }
      // Poll for completion
      const poll = setInterval(async () => {
        const st = await authorizedFetch("/api/system/backup-status");
        if (st.ok) {
          const data = await st.json();
          setBackup(data);
          if (data.state !== "running") {
            clearInterval(poll);
            setBackupTriggering(false);
          }
        }
      }, 3000);
      // Safety timeout
      setTimeout(() => { clearInterval(poll); setBackupTriggering(false); }, 120000);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Backup trigger failed");
      setBackupTriggering(false);
    }
  };

  useEffect(() => { fetchBackupStatus(); }, [fetchBackupStatus]);

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>System Health & Backup</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Full diagnostics available in the System Health page
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onNavigate?.("integrations")}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors hover:brightness-110"
            style={{
              background: "rgba(59, 130, 246, 0.15)",
              color: "var(--color-sentinel-blue)",
              border: "1px solid rgba(59, 130, 246, 0.3)",
            }}
          >
            <ExternalLink className="h-4 w-4" />
            Open System Health
          </button>
        </div>
      </div>

      <div className="p-4">
        {/* Backup Status & Trigger */}
        {backup ? (
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Archive className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                <h3 className="text-xs font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Database Backup</h3>
              </div>
              <button
                type="button"
                onClick={() => void handleTriggerBackup()}
                disabled={backupTriggering || backup.state === "running"}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
                style={{
                  background: backupTriggering ? "rgba(245, 158, 11, 0.15)" : "rgba(59, 130, 246, 0.15)",
                  color: backupTriggering ? "var(--color-sentinel-amber)" : "var(--color-sentinel-blue)",
                  border: `1px solid ${backupTriggering ? "rgba(245, 158, 11, 0.3)" : "rgba(59, 130, 246, 0.3)"}`,
                  opacity: backupTriggering ? 0.7 : 1,
                }}
              >
                <Download className={`h-3 w-3 ${backupTriggering ? "animate-pulse" : ""}`} />
                {backupTriggering ? "Running..." : "Backup Now"}
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Last Backup</p>
                <p className="text-xs font-medium" style={{
                  color: backup.last_backup_age_hours !== null && backup.last_backup_age_hours > 48
                    ? "var(--color-sentinel-red)"
                    : backup.last_backup_age_hours !== null && backup.last_backup_age_hours > 24
                      ? "var(--color-sentinel-amber)"
                      : "var(--color-sentinel-green)",
                }}>
                  {backup.last_backup
                    ? `${backup.last_backup_age_hours !== null ? (backup.last_backup_age_hours < 1 ? "< 1h ago" : `${Math.round(backup.last_backup_age_hours)}h ago`) : new Date(backup.last_backup).toLocaleDateString()}`
                    : "Never"}
                </p>
              </div>
              <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Backup Sets</p>
                <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{backup.file_count} sets</p>
              </div>
              <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Size</p>
                <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{backup.total_size_mb} MB</p>
              </div>
              <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Status</p>
                <p className="text-xs font-medium" style={{
                  color: backup.state === "running" ? "var(--color-sentinel-amber)"
                    : backup.last_result === "success" ? "var(--color-sentinel-green)"
                      : backup.last_result === "failed" ? "var(--color-sentinel-red)"
                        : "var(--color-sentinel-text-secondary)",
                }}>
                  {backup.state === "running" ? "Running..." : backup.last_result || "No runs"}
                </p>
              </div>
            </div>
            {drStatus && (
              <div className="mt-3">
                <div className="flex items-center gap-2 mb-2">
                  <ShieldCheck className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  <h3 className="text-xs font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>DR Readiness</h3>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Status</p>
                    <p className="text-xs font-medium" style={{
                      color: drStatus.status === "healthy" ? "var(--color-sentinel-green)"
                        : drStatus.status === "degraded" ? "var(--color-sentinel-amber)"
                          : "var(--color-sentinel-red)",
                    }}>
                      {drStatus.status} · {drStatus.score}
                    </p>
                  </div>
                  <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>RPO Exposure</p>
                    <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {drStatus.rpo.local_restore_exposure_label}
                    </p>
                  </div>
                  <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>DB Layer Time</p>
                    <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {drStatus.rto.last_database_layer_label}
                    </p>
                  </div>
                  <div className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                    <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Restore Target</p>
                    <p className="text-xs font-medium" style={{
                      color: drStatus.local_restore_target.last_result === "success"
                        ? "var(--color-sentinel-green)"
                        : "var(--color-sentinel-red)",
                    }}>
                      {drStatus.local_restore_target.table_count ?? 0} tables · {Object.keys(drStatus.local_restore_target.critical_row_counts ?? {}).length} checks
                    </p>
                  </div>
                </div>
              </div>
            )}
            {Object.keys(siteProgress).length > 0 && (
              <div className="mt-4">
                <div className="flex items-center gap-2 mb-2">
                  <Activity className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  <h3 className="text-xs font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Site Progress</h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.values(siteProgress).map((sp) => {
                    const stages = [sp.pls, sp.onboarding, sp.phase_promotion, sp.integrity];
                    const blocked = stages.filter((s) => s.status === "blocked");
                    const overall = blocked.length === 0 ? "✅" : "⚠️";
                    return (
                      <div key={sp.site_id} className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-xs font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                            {overall} {sp.site_id}
                          </p>
                        </div>
                        {stages.map((stage) => {
                          const dots: Record<string, string> = {
                            completed: "✅", in_progress: "🔄", blocked: "❌", not_reached: "○",
                          };
                          const failed = stage.gates.filter((g) => !g.passed);
                          return (
                            <div key={stage.stage} className="mb-2 last:mb-0">
                              <div className="flex items-center gap-1.5 mb-1">
                                <span className="text-[11px]">{dots[stage.status] || "○"}</span>
                                <span className="text-[11px] font-medium truncate" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                  {stage.stage}
                                </span>
                                {failed.length > 0 && (
                                  <span className="text-[10px] ml-auto" style={{ color: "var(--color-sentinel-amber)" }}>
                                    {failed.length}/{stage.gates.length}
                                  </span>
                                )}
                              </div>
                              {failed.length > 0 && (
                                <div className="ml-4 space-y-0.5">
                                  {failed.map((gate) => (
                                    <div key={gate.name}>
                                      <p className="text-[10px]" style={{ color: "var(--color-sentinel-red)" }}>
                                        ✗ {gate.name.replace(/_/g, " ")}
                                      </p>
                                      {gate.action && (
                                        <p className="text-[9px] ml-2" style={{ color: "var(--color-sentinel-amber)" }}>
                                          → {gate.action}
                                        </p>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                        {sp.next_actions.length > 0 && (
                          <div className="mt-2 pt-2 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
                            <p className="text-[9px] font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Next actions:</p>
                            {sp.next_actions.map((a, i) => (
                              <p key={i} className="text-[9px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                                {i + 1}. {a}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {phaseReadiness && phaseReadiness.sites.length > 0 && (
              <div className="mt-3">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  <h3 className="text-xs font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Phase Readiness</h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {phaseReadiness.sites
                    .filter((site) => site.target_phase)
                    .slice(0, 4)
                    .map((site) => {
                      const failed = site.gates.filter((gate) => !gate.passed);
                      const accent = site.eligible ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)";
                      return (
                        <div key={site.site_id} className="p-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-medium truncate" style={{ color: "var(--color-sentinel-text-primary)" }}>
                              {site.site_id} · {site.current_phase} → {site.target_phase}
                            </p>
                            {site.eligible ? (
                              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" style={{ color: accent }} />
                            ) : (
                              <AlertTriangle className="h-3.5 w-3.5 shrink-0" style={{ color: accent }} />
                            )}
                          </div>
                          <p className="text-[10px] mt-1" style={{ color: accent }}>
                            {site.gates_passed}/{site.gates_total} gates passed
                          </p>
                          {failed.length > 0 && (
                            <p className="text-[10px] mt-1 truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              Blocking: {failed.slice(0, 2).map((gate) => gate.gate.replace(/_/g, " ")).join(", ")}
                            </p>
                          )}
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Loading backup status...
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
