import { useEffect, useState } from "react";
import { Bot, Save, AlertCircle, CheckCircle, XCircle } from "lucide-react";
import { toast } from "sonner";
import { authorizedFetch } from "@/lib/api";

interface AiRuntimePolicy {
  chat_local_ai_only: boolean;
  allow_tool_calling: boolean;
  show_recommendations_in_shadow: boolean;
  ml_training_enabled: boolean;
  monthly_budget_zar: number;
  hard_cap_enforced: boolean;
}

interface MlReadiness {
  ready: boolean;
  overall: string;
  blocking_metrics: string[];
  telemetry_results: Array<{
    metric: string;
    value: number;
    state: string;
    threshold: { pass_bound: number; warn_bound: number | null; direction: string };
  }>;
}

interface AiRuntimePolicySettingsProps {
  siteId?: string;
  readOnly?: boolean;
  currentUserRole?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
}

const DEFAULT_POLICY: AiRuntimePolicy = {
  chat_local_ai_only: false,
  allow_tool_calling: true,
  show_recommendations_in_shadow: false,
  ml_training_enabled: false,
  monthly_budget_zar: 0,
  hard_cap_enforced: false,
};

const METRIC_LABELS: Record<string, string> = {
  freshness_minutes: "Data freshness",
  ingest_error_rate_pct_1h: "Ingest error rate",
  match_coverage_pct: "Match coverage",
  manual_source_pct: "Manual source %",
  unmatched_points_pct: "Unmatched points %",
  commissioning_all_gates_passed: "Commissioning gates",
  consecutive_pass_days: "Consecutive pass days",
};

export function AiRuntimePolicySettings({
  siteId,
  readOnly,
  currentUserRole,
  onError,
  onSuccess,
}: AiRuntimePolicySettingsProps) {
  const [policy, setPolicy] = useState<AiRuntimePolicy>(DEFAULT_POLICY);
  const [readiness, setReadiness] = useState<MlReadiness | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!siteId) return;

    let cancelled = false;
    setLoading(true);
    setReadiness(null);
    authorizedFetch(`/api/settings/ai-policy/${encodeURIComponent(siteId)}`)
      .then((response) => (response.ok ? response.json() : DEFAULT_POLICY))
      .then((data) => {
        if (cancelled) return;
        setPolicy({
          chat_local_ai_only: !!data.chat_local_ai_only,
          allow_tool_calling: !!data.allow_tool_calling,
          show_recommendations_in_shadow: !!data.show_recommendations_in_shadow,
          ml_training_enabled: !!data.ml_training_enabled,
          monthly_budget_zar: Number(data.monthly_budget_zar || 0),
          hard_cap_enforced: !!data.hard_cap_enforced,
        });
        if (data.ml_training_readiness) {
          setReadiness(data.ml_training_readiness);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setPolicy(DEFAULT_POLICY);
        setReadiness(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [siteId]);

  const canEdit = currentUserRole === "admin" && !readOnly;
  const mlToggleDisabled = !canEdit || loading || (!policy.ml_training_enabled && (readiness ? !readiness.ready : true));

  const savePolicy = async () => {
    if (!siteId || !canEdit) return;

    setSaving(true);
    try {
      const response = await authorizedFetch(`/api/settings/ai-policy/${encodeURIComponent(siteId)}`, {
        method: "PUT",
        body: JSON.stringify(policy),
      });
      if (!response.ok) {
        throw new Error("Failed to save AI runtime policy");
      }
      onSuccess?.();
    } catch (error) {
      onError?.(error instanceof Error ? error.message : "Failed to save AI runtime policy");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass-panel flat overflow-visible">
      <div className="p-4 border-b rounded-t-lg" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>AI Runtime Policy</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Site-scoped controls for chat execution, ML training, and shadow-mode recommendation visibility.
            </p>
          </div>
        </div>
      </div>
      <div className="p-6 space-y-4">
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1"
            checked={policy.ml_training_enabled}
            disabled={mlToggleDisabled}
            onChange={(e) => {
              const enabled = e.target.checked;
              if (enabled && readiness && !readiness.ready) {
                toast.error("ML training is not ready for this site", {
                  description: `Blocked by: ${readiness.blocking_metrics.map((m) => METRIC_LABELS[m] || m).join(", ")}`,
                });
                return;
              }
              setPolicy((prev) => ({ ...prev, ml_training_enabled: enabled }));
              toast.info(enabled ? "ML training enabled (unsaved)" : "ML training disabled (unsaved)");
            }}
          />
          <div className="flex-1">
            <div style={{ color: "var(--color-sentinel-text-primary)" }}>Enable ML training for this site</div>
            <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Turn this on only after bridge telemetry is stable and onboarding data looks clean.
            </div>

            {/* Readiness status banner */}
            {readiness && readiness.ready && (
              <div className="mt-2 flex items-center gap-2 rounded px-3 py-2 text-xs" style={{ background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                <CheckCircle className="h-3.5 w-3.5" style={{ color: "var(--color-sentinel-green)" }} />
                <span style={{ color: "var(--color-sentinel-green)" }}>All telemetry gates passed — ML training can be enabled</span>
              </div>
            )}
            {readiness && !readiness.ready && (
              <div className="mt-2 p-2 rounded text-xs" style={{ background: "rgba(239, 68, 68, 0.1)", color: "var(--color-sentinel-red)" }}>
                <div className="flex items-center gap-1 font-medium mb-1">
                  <AlertCircle className="h-3 w-3" />
                  ML training not ready — {readiness.blocking_metrics.length} telemetry metric(s) need attention
                </div>
                <ul className="space-y-0.5 ml-4">
                  {readiness.blocking_metrics.map((m) => (
                    <li key={m}>{METRIC_LABELS[m] || m}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Telemetry results grid — visible when readiness loaded */}
            {readiness && (
              <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-1.5">
                {readiness.telemetry_results.map((rule) => {
                  const pass = rule.state === "pass";
                  const isWarn = rule.state === "warn";
                  return (
                    <div key={rule.metric} className="flex items-center gap-1.5 rounded px-2 py-1.5 text-xs" style={{
                      background: pass ? "rgba(16, 185, 129, 0.08)" : isWarn ? "rgba(245, 158, 11, 0.08)" : "rgba(239, 68, 68, 0.08)",
                      color: pass ? "var(--color-sentinel-green)" : isWarn ? "var(--color-sentinel-orange)" : "var(--color-sentinel-red)",
                    }}>
                      {pass ? <CheckCircle className="h-3 w-3 shrink-0" /> : <XCircle className="h-3 w-3 shrink-0" />}
                      <span className="truncate">{METRIC_LABELS[rule.metric] || rule.metric}</span>
                      <span className="ml-auto font-medium">{rule.value?.toFixed?.(1) ?? rule.value}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </label>

        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1"
            checked={policy.chat_local_ai_only}
            disabled={!canEdit || loading}
            onChange={(e) => setPolicy((prev) => ({ ...prev, chat_local_ai_only: e.target.checked }))}
          />
          <div>
            <div style={{ color: "var(--color-sentinel-text-primary)" }}>Force local AI chat only</div>
            <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Disables cloud LLM chat paths for this site.
            </div>
          </div>
        </label>

        <div className="space-y-2">
          <div style={{ color: "var(--color-sentinel-text-primary)" }}>Monthly AI budget (ZAR)</div>
          <input
            type="number"
            min={0}
            step={10}
            value={policy.monthly_budget_zar}
            disabled={!canEdit || loading}
            onChange={(e) =>
              setPolicy((prev) => ({
                ...prev,
                monthly_budget_zar: Math.max(0, Number(e.target.value || 0)),
              }))
            }
            className="w-full px-3 py-2 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1"
              checked={policy.hard_cap_enforced}
              disabled={!canEdit || loading || policy.monthly_budget_zar <= 0}
              onChange={(e) => setPolicy((prev) => ({ ...prev, hard_cap_enforced: e.target.checked }))}
            />
            <div>
              <div style={{ color: "var(--color-sentinel-text-primary)" }}>Enforce hard cap</div>
              <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Block paid AI chat calls when site monthly budget is exceeded.
              </div>
            </div>
          </label>
        </div>

        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1"
            checked={policy.allow_tool_calling}
            disabled={!canEdit || loading || policy.chat_local_ai_only}
            onChange={(e) => setPolicy((prev) => ({ ...prev, allow_tool_calling: e.target.checked }))}
          />
          <div>
            <div style={{ color: "var(--color-sentinel-text-primary)" }}>Allow chat tool-calling</div>
            <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Enables tool-based actions from chat (disabled when local-only is forced).
            </div>
          </div>
        </label>

        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            className="mt-1"
            checked={policy.show_recommendations_in_shadow}
            disabled={!canEdit || loading}
            onChange={(e) => setPolicy((prev) => ({ ...prev, show_recommendations_in_shadow: e.target.checked }))}
          />
          <div>
            <div style={{ color: "var(--color-sentinel-text-primary)" }}>Show recommendations in shadow mode</div>
            <div className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Keep hidden for learning-only shadow mode; enable only when you want advisory visibility.
            </div>
          </div>
        </label>

        <div className="pt-2">
          <button
            type="button"
            disabled={!canEdit || saving || loading || !siteId}
            onClick={savePolicy}
            className="px-4 py-2 rounded inline-flex items-center gap-2 disabled:opacity-50"
            style={{ background: "var(--color-sentinel-blue)", color: "white" }}
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : "Save AI policy"}
          </button>
        </div>
      </div>
    </div>
  );
}
