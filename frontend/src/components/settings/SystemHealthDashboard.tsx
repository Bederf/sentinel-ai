import { useState, useEffect, useCallback } from "react";
import { Activity, ExternalLink, Archive, Download } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

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
  onNavigate?: (view: import("../../lib/navigation").View) => void;
}

export function SystemHealthDashboard({ onError, onNavigate }: SystemHealthDashboardProps) {
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

  useEffect(() => { fetchBackupStatus(); }, [fetchBackupStatus]);

  return (
    <div className="glass-panel overflow-hidden">
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
