import { useState, useEffect, useCallback } from "react";
import { Activity, RefreshCw, Database, Wifi, HardDrive, Brain, Cpu, Server, Radio, Wrench, Bot, FileSearch, Archive, Download } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface ComponentDetail {
  status: "healthy" | "degraded" | "critical";
  note: string;
}

interface HealthData {
  timestamp: string;
  overall_status: string;
  overall_score: number;
  component_scores: Record<string, number>;
  component_details: Record<string, ComponentDetail>;
  errors: Array<{ component: string; error: string }>;
}

interface BackupStatus {
  state: "idle" | "running";
  last_backup: string | null;
  last_backup_age_hours: number | null;
  file_count: number;
  total_size_mb: number;
  last_result: string | null;
}

interface SystemHealthDashboardProps {
  onError?: (error: string) => void;
}

// Component groupings for display
const GROUPS = [
  {
    title: "Infrastructure",
    color: "var(--color-sentinel-blue)",
    bgColor: "rgba(59, 130, 246, 0.15)",
    components: [
      { key: "supabase", label: "Supabase", icon: Database },
      { key: "redis_cache", label: "Redis Cache", icon: Server },
      { key: "disk", label: "Disk Space", icon: HardDrive },
      { key: "llm", label: "LLM Provider", icon: Bot },
    ],
  },
  {
    title: "Integrations",
    color: "var(--color-sentinel-green)",
    bgColor: "rgba(16, 185, 129, 0.15)",
    components: [
      { key: "event_bus", label: "Event Bus", icon: Radio },
      { key: "n8n", label: "n8n Workflows", icon: Wifi },
      { key: "servicenow", label: "ServiceNow", icon: Wrench },
      { key: "notifications", label: "Notifications", icon: Radio },
      { key: "device_manager", label: "Device Manager", icon: Cpu },
    ],
  },
  {
    title: "Intelligence",
    color: "rgb(168, 85, 247)",
    bgColor: "rgba(168, 85, 247, 0.15)",
    components: [
      { key: "ml_models", label: "ML Models", icon: Brain },
      { key: "background_jobs", label: "Background Jobs", icon: Activity },
      { key: "rag", label: "RAG Documents", icon: FileSearch },
    ],
  },
];

export function SystemHealthDashboard({ onError }: SystemHealthDashboardProps) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [backup, setBackup] = useState<BackupStatus | null>(null);
  const [backupTriggering, setBackupTriggering] = useState(false);

  const fetchBackupStatus = useCallback(async () => {
    try {
      const res = await authorizedFetch("/api/system/backup-status");
      if (res.ok) setBackup(await res.json());
    } catch { /* ignore */ }
  }, []);

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

  const fetchHealth = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true);
    try {
      const response = await authorizedFetch("/api/system/health/extended");
      if (!response.ok) {
        // Fallback to standard health
        const fallback = await authorizedFetch("/api/system/health");
        if (fallback.ok) {
          setHealth(await fallback.json());
          return;
        }
        throw new Error("Failed to fetch health");
      }
      setHealth(await response.json());
    } catch {
      onError?.("Failed to load system health");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [onError]);

  useEffect(() => { fetchHealth(); fetchBackupStatus(); }, [fetchHealth, fetchBackupStatus]);

  const statusColor = (status: string) => {
    if (status === "healthy") return "var(--color-sentinel-green)";
    if (status === "degraded") return "var(--color-sentinel-amber)";
    return "var(--color-sentinel-red)";
  };

  const scoreBg = (score: number) => {
    if (score >= 80) return "rgba(16, 185, 129, 0.15)";
    if (score >= 60) return "rgba(245, 158, 11, 0.15)";
    return "rgba(220, 38, 38, 0.15)";
  };

  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>System Health</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Real-time status of all system components
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {health && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full" style={{ background: scoreBg(health.overall_score) }}>
                <div className="h-2 w-2 rounded-full" style={{ background: statusColor(health.overall_status) }} />
                <span className="text-sm font-semibold" style={{ color: statusColor(health.overall_status) }}>
                  {health.overall_score}%
                </span>
              </div>
            )}
            <button
              type="button"
              onClick={() => void fetchHealth(true)}
              disabled={refreshing}
              className="p-2 rounded transition-colors hover:brightness-110"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <div className="text-center py-6">
            <div className="animate-spin h-6 w-6 border-2 rounded-full mx-auto mb-2" style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Running diagnostics...</p>
          </div>
        ) : health ? (
          <div className="space-y-5">
            {GROUPS.map((group) => {
              const availableComponents = group.components.filter(
                (c) => c.key in (health.component_details || {})
              );
              if (availableComponents.length === 0) return null;

              return (
                <div key={group.title}>
                  <h3 className="text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: group.color }}>
                    {group.title}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                    {availableComponents.map((comp) => {
                      const detail = health.component_details[comp.key];
                      const score = health.component_scores[comp.key] ?? 0;
                      const Icon = comp.icon;

                      return (
                        <div
                          key={comp.key}
                          className="flex items-start gap-3 p-3 rounded-lg"
                          style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}
                        >
                          <div className="p-1.5 rounded" style={{ background: group.bgColor, color: group.color }}>
                            <Icon className="h-3.5 w-3.5" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                                {comp.label}
                              </span>
                              <div className="flex items-center gap-1">
                                <div className="h-1.5 w-1.5 rounded-full" style={{ background: statusColor(detail?.status || "critical") }} />
                                <span className="text-[10px] font-medium" style={{ color: statusColor(detail?.status || "critical") }}>
                                  {score}
                                </span>
                              </div>
                            </div>
                            <p className="text-[10px] mt-0.5 truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                              {detail?.note || "No data"}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {/* Errors */}
            {health.errors && health.errors.length > 0 && (
              <div className="mt-3 p-3 rounded-lg" style={{ background: "rgba(220, 38, 38, 0.08)", border: "1px solid rgba(220, 38, 38, 0.2)" }}>
                <h4 className="text-xs font-semibold mb-1" style={{ color: "var(--color-sentinel-red)" }}>Errors</h4>
                {health.errors.map((err, i) => (
                  <p key={i} className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    <span className="font-mono" style={{ color: "var(--color-sentinel-red)" }}>{err.component}</span>: {err.error}
                  </p>
                ))}
              </div>
            )}

            {/* Timestamp */}
            <p className="text-[10px] text-right" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Last checked: {new Date(health.timestamp).toLocaleTimeString()}
            </p>
          </div>
        ) : (
          <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Unable to load system health data
          </p>
        )}

        {/* Backup Status & Trigger */}
        {backup && (
          <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--glass-border)" }}>
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
                <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Files</p>
                <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{backup.file_count} tables</p>
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
          </div>
        )}
      </div>
    </div>
  );
}
