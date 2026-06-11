import { useEffect, useState } from "react";
import { Shield, Save, AlertTriangle, CheckCircle2 } from "lucide-react";
import { authorizedFetch } from "@/lib/api";

interface AegisSettingsData {
  site_id: string;
  aegis_bess_writer_enabled: boolean;
  current_stage: string;
  execution_allowed: boolean;
  gate_status: "open" | "closed";
  warning?: string | null;
}

interface AegisSettingsProps {
  siteId?: string;
  readOnly?: boolean;
  currentUserRole?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  embedded?: boolean;
}

export function AegisSettings({
  siteId,
  readOnly,
  currentUserRole,
  onError,
  onSuccess,
  embedded = false,
}: AegisSettingsProps) {
  const [data, setData] = useState<AegisSettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    if (!siteId) return;

    setLoading(true);
    authorizedFetch(`/api/settings/aegis/${encodeURIComponent(siteId)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((result) => {
        if (result) {
          setData(result);
          setEnabled(result.aegis_bess_writer_enabled);
        }
      })
      .catch(() => {
        onError?.("Failed to load AEGIS settings");
      })
      .finally(() => setLoading(false));
  }, [siteId, onError]);

  const canEdit = currentUserRole === "admin" && !readOnly;

  const saveSettings = async () => {
    if (!siteId || !canEdit || !data) return;

    setSaving(true);
    try {
      const response = await authorizedFetch(
        `/api/settings/aegis/${encodeURIComponent(siteId)}`,
        {
          method: "PUT",
          body: JSON.stringify({ aegis_bess_writer_enabled: enabled }),
        }
      );
      if (!response.ok) {
        throw new Error("Failed to save AEGIS settings");
      }
      const result = await response.json();
      setData(result);
      onSuccess?.();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Failed to save AEGIS settings");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    const skeleton = (
      <div className="animate-pulse space-y-4">
        <div className="h-4 bg-slate-700 rounded w-1/3" />
        <div className="h-8 bg-slate-700 rounded w-1/2" />
      </div>
    );
    if (embedded) return skeleton;
    return <div className="glass-panel p-6">{skeleton}</div>;
  }

  if (!data) {
    if (embedded) return null;
    return (
      <div className="glass-panel p-6">
        <p className="text-slate-400">Unable to load AEGIS settings</p>
      </div>
    );
  }

  const gateOpen = data.gate_status === "open";

  const content = (
    <div className="space-y-6">
      {/* Gate Status Banner */}
      <div
        className="p-4 rounded-lg border flex items-start gap-3"
        style={{
          background: gateOpen
            ? "rgba(34, 197, 94, 0.1)"
            : "rgba(234, 179, 8, 0.1)",
          borderColor: gateOpen ? "rgba(34, 197, 94, 0.3)" : "rgba(234, 179, 8, 0.3)",
        }}
      >
        {gateOpen ? (
          <CheckCircle2 className="h-5 w-5 mt-0.5" style={{ color: "#22c55e" }} />
        ) : (
          <AlertTriangle className="h-5 w-5 mt-0.5" style={{ color: "#eab308" }} />
        )}
        <div>
          <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Gate Status: {gateOpen ? "OPEN" : "CLOSED"}
          </p>
          <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {gateOpen
              ? "AEGIS can execute BESS write commands when site is in supervised or automatic mode"
              : "AEGIS write commands are blocked — toggle the switch below to enable"}
          </p>
        </div>
      </div>

      {/* Site Mode Status */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-4 rounded-lg" style={{ background: "var(--color-sentinel-bg-subtle)" }}>
          <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Site Mode
          </p>
          <p className="text-lg font-mono font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {data.current_stage}
          </p>
        </div>
        <div className="p-4 rounded-lg" style={{ background: "var(--color-sentinel-bg-subtle)" }}>
          <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Execution
          </p>
          <p className="text-lg font-semibold" style={{ color: data.execution_allowed ? "#22c55e" : "#ef4444" }}>
            {data.execution_allowed ? "ALLOWED" : "BLOCKED"}
          </p>
        </div>
        <div className="p-4 rounded-lg" style={{ background: "var(--color-sentinel-bg-subtle)" }}>
          <p className="text-xs uppercase tracking-wider mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Writer Flag
          </p>
          <p className="text-lg font-semibold" style={{ color: data.aegis_bess_writer_enabled ? "#22c55e" : "#ef4444" }}>
            {data.aegis_bess_writer_enabled ? "ENABLED" : "DISABLED"}
          </p>
        </div>
      </div>

      {/* Toggle Control */}
      <div className="flex items-center justify-between py-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div>
          <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Enable AEGIS Writer
          </p>
          <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {canEdit
              ? "Toggle to allow AEGIS to send dispatch commands to BESS (requires supervised or automatic mode)"
              : "Admin role required to modify this setting"}
          </p>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            disabled={!canEdit}
          />
          <div
            className="w-11 h-6 rounded-full peer transition-colors"
            style={{
              backgroundColor: enabled ? "#22c55e" : "#475569",
              opacity: canEdit ? 1 : 0.5,
            }}
          />
          <div
            className="absolute left-0.5 top-0.5 bg-white w-5 h-5 rounded-full transition-transform"
            style={{
              transform: enabled ? "translateX(20px)" : "translateX(0)",
            }}
          />
        </label>
      </div>

      {/* Warning if enabling while not in supervised/automatic */}
      {data.warning && (
        <div
          className="p-4 rounded-lg flex items-start gap-3"
          style={{
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
          }}
        >
          <AlertTriangle className="h-5 w-5 mt-0.5" style={{ color: "#ef4444" }} />
          <div>
            <p className="font-medium" style={{ color: "#ef4444" }}>
              Execution Blocked
            </p>
            <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {data.warning}
            </p>
          </div>
        </div>
      )}

      {/* Save Button */}
      {canEdit && (
        <div className="flex justify-end pt-4 border-t" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <button
            onClick={saveSettings}
            disabled={saving || enabled === data.aegis_bess_writer_enabled}
            className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors"
            style={{
              backgroundColor:
                enabled === data.aegis_bess_writer_enabled
                  ? "#475569"
                  : "#22c55e",
              color: "#fff",
              cursor:
                saving || enabled === data.aegis_bess_writer_enabled
                  ? "not-allowed"
                  : "pointer",
            }}
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      )}
    </div>
  );

  if (embedded) {
    return content;
  }

  return (
    <div className="glass-panel overflow-visible">
      <div className="p-4 border-b rounded-t-lg" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: gateOpen ? "rgba(34, 197, 94, 0.15)" : "rgba(234, 179, 8, 0.15)", color: gateOpen ? "#22c55e" : "#eab308" }}>
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>AEGIS BESS Control</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Enable automatic BESS dispatch write commands</p>
          </div>
        </div>
      </div>
      <div className="p-6">
        {content}
      </div>
    </div>
  );
}
