import { useState, useEffect, useCallback } from "react";
import { Shield, Plus, UserX, Edit2, X, Save, Mail, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface Manager {
  id: string;
  name: string;
  email: string;
  phone?: string;
  telegram_id?: string;
  site_id?: string;
  role: string;
  active: boolean;
  created_at?: string;
}

interface ManagerRegistryProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

export function ManagerRegistry({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: ManagerRegistryProps) {
  const [managers, setManagers] = useState<Manager[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Add form state
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newTelegram, setNewTelegram] = useState("");
  const [newRole, setNewRole] = useState("manager");
  const [adding, setAdding] = useState(false);

  const [showInvite, setShowInvite] = useState(false);
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("operator");
  const [inviteSiteId, setInviteSiteId] = useState(siteId);
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [inviteSuccess, setInviteSuccess] = useState("");

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editRole, setEditRole] = useState("manager");

  const fetchManagers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authorizedFetch(`/api/managers?site_id=${siteId}`);
      if (res.ok) {
        const data = await res.json();
        setManagers(data.managers || []);
      } else {
        throw new Error("Failed to load managers");
      }
    } catch {
      onError?.("Failed to load managers");
    } finally {
      setLoading(false);
    }
  }, [siteId, onError]);

  useEffect(() => { fetchManagers(); }, [fetchManagers]);

  const handleAdd = async () => {
    if (!newName.trim() || !newEmail.trim()) return;
    setAdding(true);
    try {
      const res = await authorizedFetch("/api/managers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          email: newEmail.trim(),
          phone: newPhone.trim() || undefined,
          telegram_id: newTelegram.trim() || undefined,
          site_id: siteId,
          role: newRole,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to create manager");
      }
      setNewName(""); setNewEmail(""); setNewPhone(""); setNewTelegram("");
      setShowAdd(false);
      await fetchManagers();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to create manager");
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (mgr: Manager) => {
    setEditingId(mgr.id);
    setEditName(mgr.name);
    setEditEmail(mgr.email);
    setEditPhone(mgr.phone || "");
    setEditRole(mgr.role);
  };

  const handleUpdate = async (mgrId: string) => {
    try {
      const res = await authorizedFetch(`/api/managers/${mgrId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName.trim() || undefined,
          email: editEmail.trim() || undefined,
          phone: editPhone.trim() || undefined,
          role: editRole || undefined,
        }),
      });
      if (!res.ok) throw new Error("Failed to update");
      setEditingId(null);
      await fetchManagers();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to update manager");
    }
  };

  const handleInvite = async () => {
    if (!inviteName.trim() || !inviteEmail.trim()) return;
    setInviting(true);
    setInviteError("");
    setInviteSuccess("");
    try {
      const res = await authorizedFetch("/api/auth/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: inviteEmail.trim(),
          full_name: inviteName.trim(),
          role: inviteRole,
          site_id: inviteSiteId || siteId,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to send invite");
      }
      setInviteSuccess(`Invite sent to ${inviteEmail}`);
      setInviteName(""); setInviteEmail("");
      setTimeout(() => { setShowInvite(false); setInviteSuccess(""); }, 3000);
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : "Failed to send invite");
    } finally {
      setInviting(false);
    }
  };

  const handleDelete = async (mgr: Manager) => {
    if (!confirm(`Deactivate ${mgr.name}?`)) return;
    try {
      const res = await authorizedFetch(`/api/managers/${mgr.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to deactivate");
      await fetchManagers();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to deactivate manager");
    }
  };

  const roleColor = (role: string) => {
    const map: Record<string, string> = {
      admin: "var(--color-sentinel-red)",
      operator: "var(--color-sentinel-amber)",
      manager: "var(--color-sentinel-blue)",
    };
    return map[role] || "var(--color-sentinel-text-secondary)";
  };

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Manager Registry</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Site managers and operators who receive infrastructure alerts
              </p>
            </div>
          </div>
          {!readOnly && (
            <button type="button" onClick={() => setShowAdd(!showAdd)}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)" }}
            >
              <Plus className="h-3 w-3" />
              Add Manager
            </button>
          )}
          {!readOnly && (
            <button type="button" onClick={() => { setShowInvite(true); setInviteError(""); setInviteSuccess(""); }}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)" }}
            >
              <Mail className="h-3 w-3" />
              Invite Manager
            </button>
          )}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Add Form */}
        {showAdd && !readOnly && (
          <div className="p-4 rounded-lg space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Name *</label>
                <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Jane Manager" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Email *</label>
                <input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="jane@sentinel-ai.co.za" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Phone</label>
                <input type="tel" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="+27721234567" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Telegram ID</label>
                <input type="text" value={newTelegram} onChange={(e) => setNewTelegram(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="8359288792" />
              </div>
            </div>
            <div>
              <label className="block text-xs mb-1.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>Role</label>
              <div className="flex gap-2">
                {["manager", "operator", "admin"].map((r) => (
                  <button key={r} type="button" onClick={() => setNewRole(r)}
                    className="px-3 py-1 rounded text-xs font-medium transition-colors"
                    style={{
                      background: newRole === r ? `${roleColor(r)}20` : "transparent",
                      color: roleColor(r),
                      border: `1px solid ${newRole === r ? roleColor(r) : "var(--glass-border)"}`,
                    }}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Cancel</button>
              <button type="button" onClick={() => void handleAdd()} disabled={adding || !newName.trim() || !newEmail.trim()}
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium"
                style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)", opacity: adding || !newName.trim() || !newEmail.trim() ? 0.5 : 1 }}
              >
                <Save className="h-3 w-3" />
                {adding ? "Adding..." : "Add Manager"}
              </button>
            </div>
          </div>
        )}

        {/* Invite Form */}
        {showInvite && !readOnly && (
          <div className="p-4 rounded-lg space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
            <div className="flex items-center gap-2 mb-2">
              <Mail className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
              <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Invite Manager</span>
            </div>
            <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              An invite link will be sent to the email address. The recipient can set their own password.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Full Name *</label>
                <input type="text" value={inviteName} onChange={(e) => setInviteName(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Jane Manager" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Email *</label>
                <input type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="jane@example.com" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Role</label>
                <div className="flex gap-2">
                  {["operator", "manager", "admin"].map((r) => (
                    <button key={r} type="button" onClick={() => setInviteRole(r)}
                      className="px-3 py-1 rounded text-xs font-medium transition-colors"
                      style={{
                        background: inviteRole === r ? `${roleColor(r)}20` : "transparent",
                        color: roleColor(r),
                        border: `1px solid ${inviteRole === r ? roleColor(r) : "var(--glass-border)"}`,
                      }}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Site</label>
                <input type="text" value={inviteSiteId} onChange={(e) => setInviteSiteId(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="site-002" />
              </div>
            </div>
            {inviteError && (
              <div className="flex items-center gap-1 text-xs" style={{ color: "var(--color-sentinel-red)" }}>
                <AlertCircle className="h-3 w-3" />
                {inviteError}
              </div>
            )}
            {inviteSuccess && (
              <div className="flex items-center gap-1 text-xs" style={{ color: "var(--color-sentinel-green)" }}>
                <CheckCircle2 className="h-3 w-3" />
                {inviteSuccess}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowInvite(false)} className="px-3 py-1.5 rounded text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Cancel</button>
              <button type="button" onClick={() => void handleInvite()} disabled={inviting || !inviteName.trim() || !inviteEmail.trim()}
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium"
                style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)", opacity: inviting || !inviteName.trim() || !inviteEmail.trim() ? 0.5 : 1 }}
              >
                {inviting ? <><Loader2 className="h-3 w-3 animate-spin" /> Sending...</> : <><Mail className="h-3 w-3" /> Send Invite</>}
              </button>
            </div>
          </div>
        )}

        {/* Manager List */}
        {loading ? (
          <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading managers...</p>
        ) : managers.length === 0 ? (
          <div className="text-center py-8">
            <Shield className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-text-secondary)", opacity: 0.3 }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No managers registered</p>
            <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Add managers to enable alert routing and dashboard notifications</p>
          </div>
        ) : (
          <div className="space-y-2">
            {managers.map((mgr) => {
              const isEditing = editingId === mgr.id;

              return (
                <div key={mgr.id} className="p-3 rounded-lg" style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--glass-border)",
                  opacity: mgr.active ? 1 : 0.5,
                }}>
                  {isEditing ? (
                    <div className="space-y-2">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} placeholder="Name" />
                        <input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} placeholder="Email" />
                        <input type="tel" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} placeholder="Phone" />
                        <select value={editRole} onChange={(e) => setEditRole(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle}>
                          <option value="manager">Manager</option>
                          <option value="operator">Operator</option>
                          <option value="admin">Admin</option>
                        </select>
                      </div>
                      <div className="flex justify-end gap-1">
                        <button type="button" onClick={() => setEditingId(null)} className="p-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          <X className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => void handleUpdate(mgr.id)} className="p-1" style={{ color: "var(--color-sentinel-green)" }}>
                          <Save className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{mgr.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${roleColor(mgr.role)}15`, color: roleColor(mgr.role) }}>{mgr.role}</span>
                          {!mgr.active && <span className="text-[10px] px-1 py-0.5 rounded" style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}>inactive</span>}
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{mgr.email}</span>
                          {mgr.phone && <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{mgr.phone}</span>}
                          {mgr.telegram_id && <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>TG: {mgr.telegram_id}</span>}
                        </div>
                      </div>
                      {!readOnly && (
                        <div className="flex items-center gap-1">
                          <button type="button" onClick={() => startEdit(mgr)} className="p-1" style={{ color: "var(--color-sentinel-blue)" }} title="Edit">
                            <Edit2 className="h-3.5 w-3.5" />
                          </button>
                          <button type="button" onClick={() => void handleDelete(mgr)} className="p-1"
                            style={{ color: "var(--color-sentinel-red)" }}
                            title="Deactivate"
                          >
                            <UserX className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
