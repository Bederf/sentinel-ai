import { useState, useEffect, useCallback } from "react";
import { Route, Plus, Trash2, ToggleLeft, ToggleRight } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface RoutingRule {
  id: string;
  name: string;
  enabled: boolean;
  severity: string[];
  equipment_types: string[];
  channels: string[];
  recipient_roles: string[];
  escalation_minutes: number | null;
  escalation_to_roles: string[];
  created_at?: string;
}

interface AlertRoutingRulesProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
  embedded?: boolean;
}

const SEVERITY_OPTIONS = ["critical", "warning", "info"];
const CHANNEL_OPTIONS = ["telegram", "whatsapp", "email", "sms"];
const ROLE_OPTIONS = ["technician", "supervisor", "manager", "admin"];

export function AlertRoutingRules({ siteId, onError, onSuccess, readOnly = false, embedded = false }: AlertRoutingRulesProps) {
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);

  // New rule form state
  const [newName, setNewName] = useState("");
  const [newSeverity, setNewSeverity] = useState<string[]>(["critical"]);
  const [newChannels, setNewChannels] = useState<string[]>(["telegram"]);
  const [newRoles, setNewRoles] = useState<string[]>(["technician"]);
  const [newEscalation, setNewEscalation] = useState("");

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const query = siteId ? `?site_id=${encodeURIComponent(siteId)}` : "";
      const response = await authorizedFetch(`/api/alert-routing/rules${query}`);
      if (!response.ok) throw new Error("Failed to fetch routing rules");
      const data = await response.json();
      setRules(data.rules || []);
    } catch {
      onError?.("Failed to load alert routing rules");
    } finally {
      setLoading(false);
    }
  }, [onError, siteId]);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const toggleMulti = (arr: string[], val: string): string[] =>
    arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val];

  const handleAdd = async () => {
    if (!newName.trim() || newSeverity.length === 0 || newChannels.length === 0) return;
    try {
      const response = await authorizedFetch("/api/alert-routing/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          severity: newSeverity,
          channels: newChannels,
          recipient_roles: newRoles,
          escalation_minutes: newEscalation ? parseInt(newEscalation) : null,
          escalation_to_roles: newEscalation ? ["supervisor", "admin"] : [],
          site_ids: siteId ? [siteId] : [],
        }),
      });
      if (!response.ok) throw new Error("Failed to create rule");
      setNewName(""); setNewSeverity(["critical"]); setNewChannels(["telegram"]); setNewRoles(["technician"]); setNewEscalation("");
      setShowAddForm(false);
      await fetchRules();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to create rule");
    }
  };

  const handleToggle = async (ruleId: string, currentEnabled: boolean) => {
    try {
      const response = await authorizedFetch(`/api/alert-routing/rules/${ruleId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
      if (!response.ok) throw new Error("Failed to update rule");
      await fetchRules();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to toggle rule");
    }
  };

  const handleDelete = async (ruleId: string) => {
    try {
      const response = await authorizedFetch(`/api/alert-routing/rules/${ruleId}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Failed to delete rule");
      await fetchRules();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to delete rule");
    }
  };

  const severityColor = (s: string) => {
    if (s === "critical") return "var(--color-sentinel-red)";
    if (s === "warning") return "var(--color-sentinel-amber)";
    return "var(--color-sentinel-blue)";
  };

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  const rulesContent = (
    <div className="space-y-3">
      {showAddForm && !readOnly && (
        <div className="p-4 rounded-lg space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
          <div>
            <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Rule Name</label>
            <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="e.g. Chiller faults to HVAC team" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Severity</label>
              <div className="flex flex-wrap gap-1">
                {SEVERITY_OPTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => setNewSeverity(toggleMulti(newSeverity, s))}
                    className="px-2 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: newSeverity.includes(s) ? `${severityColor(s)}22` : "transparent", color: severityColor(s), border: `1px solid ${newSeverity.includes(s) ? severityColor(s) : "var(--glass-border)"}` }}
                  >{s}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Channels</label>
              <div className="flex flex-wrap gap-1">
                {CHANNEL_OPTIONS.map((c) => (
                  <button key={c} type="button" onClick={() => setNewChannels(toggleMulti(newChannels, c))}
                    className="px-2 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: newChannels.includes(c) ? "rgba(59, 130, 246, 0.15)" : "transparent", color: "var(--color-sentinel-blue)", border: `1px solid ${newChannels.includes(c) ? "var(--color-sentinel-blue)" : "var(--glass-border)"}` }}
                  >{c}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Recipients</label>
              <div className="flex flex-wrap gap-1">
                {ROLE_OPTIONS.map((r) => (
                  <button key={r} type="button" onClick={() => setNewRoles(toggleMulti(newRoles, r))}
                    className="px-2 py-0.5 rounded text-[10px] font-medium"
                    style={{ background: newRoles.includes(r) ? "rgba(16, 185, 129, 0.15)" : "transparent", color: "var(--color-sentinel-green)", border: `1px solid ${newRoles.includes(r) ? "var(--color-sentinel-green)" : "var(--glass-border)"}` }}
                  >{r}</button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex items-end gap-3">
            <div>
              <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Escalation (minutes)</label>
              <input type="number" value={newEscalation} onChange={(e) => setNewEscalation(e.target.value)} className="rounded px-3 py-1.5 text-xs w-24" style={inputStyle} placeholder="e.g. 15" min={0} />
            </div>
            <button type="button" onClick={() => void handleAdd()} disabled={!newName.trim()} className="px-3 py-1.5 rounded text-xs font-medium" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)", opacity: !newName.trim() ? 0.5 : 1 }}>Create Rule</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading rules...</p>
      ) : rules.length === 0 ? (
        <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>No routing rules configured</p>
      ) : (
        rules.map((rule) => (
          <div key={rule.id} className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: rule.enabled ? 1 : 0.5 }}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{rule.name}</span>
                  {!rule.enabled && <span className="text-[10px] px-1 py-0.5 rounded" style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}>disabled</span>}
                </div>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {rule.severity.map((s) => (
                    <span key={s} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${severityColor(s)}15`, color: severityColor(s) }}>{s}</span>
                  ))}
                  <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>→</span>
                  {rule.channels.map((c) => (
                    <span key={c} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(59, 130, 246, 0.1)", color: "var(--color-sentinel-blue)" }}>{c}</span>
                  ))}
                  <span className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>→</span>
                  {rule.recipient_roles.map((r) => (
                    <span key={r} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(16, 185, 129, 0.1)", color: "var(--color-sentinel-green)" }}>{r}</span>
                  ))}
                </div>
                {rule.escalation_minutes && (
                  <p className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-amber)" }}>
                    Escalates after {rule.escalation_minutes}min to {rule.escalation_to_roles.join(", ")}
                  </p>
                )}
              </div>
              {!readOnly && (
                <div className="flex items-center gap-1">
                  <button type="button" onClick={() => void handleToggle(rule.id, rule.enabled)} className="p-1" style={{ color: rule.enabled ? "var(--color-sentinel-green)" : "var(--color-sentinel-text-secondary)" }} aria-label={rule.enabled ? "Disable rule" : "Enable rule"}>
                    {rule.enabled ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
                  </button>
                  <button type="button" onClick={() => void handleDelete(rule.id)} className="p-1" style={{ color: "var(--color-sentinel-red)" }} aria-label="Delete rule">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );

  if (embedded) {
    return rulesContent;
  }

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}>
              <Route className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Alert Routing Rules</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Configure how alerts are routed to channels and recipients
              </p>
            </div>
          </div>
          {!readOnly && (
            <button
              type="button"
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)" }}
            >
              <Plus className="h-3 w-3" />
              Add Rule
            </button>
          )}
        </div>
      </div>
      <div className="p-4">
        {rulesContent}
      </div>
    </div>
  );
}
