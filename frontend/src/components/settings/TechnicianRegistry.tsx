import { useState, useEffect, useCallback } from "react";
import { Users, Plus, UserCheck, UserX, Edit2, X, Save } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface Technician {
  id: string;
  code?: string;
  name: string;
  email: string;
  phone?: string;
  active: boolean;
  specialties: string[];
  channels: Array<{ channel_type: string; is_verified: boolean }>;
  telegram_id?: string;
}

interface Specialty {
  id: string;
  label: string;
  equipment_types: string[];
}

interface TechnicianRegistryProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

export function TechnicianRegistry({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: TechnicianRegistryProps) {
  const [technicians, setTechnicians] = useState<Technician[]>([]);
  const [specialties, setSpecialties] = useState<Specialty[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Add form state
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newTelegram, setNewTelegram] = useState("");
  const [newSpecs, setNewSpecs] = useState<string[]>(["general"]);
  const [adding, setAdding] = useState(false);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editSpecs, setEditSpecs] = useState<string[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [techRes, specRes] = await Promise.all([
        authorizedFetch(`/api/technicians?site_id=${siteId}`),
        authorizedFetch("/api/technicians/specialties"),
      ]);
      if (techRes.ok) {
        const data = await techRes.json();
        setTechnicians(data.technicians || []);
      }
      if (specRes.ok) {
        const data = await specRes.json();
        setSpecialties(data.specialties || []);
      }
    } catch {
      onError?.("Failed to load technicians");
    } finally {
      setLoading(false);
    }
  }, [siteId, onError]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleSpec = (arr: string[], val: string): string[] =>
    arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val];

  const handleAdd = async () => {
    if (!newName.trim() || !newEmail.trim()) return;
    setAdding(true);
    try {
      const res = await authorizedFetch("/api/technicians", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          email: newEmail.trim(),
          phone: newPhone.trim() || undefined,
          telegram_id: newTelegram.trim() || undefined,
          specialties: newSpecs.length ? newSpecs : ["general"],
          site_id: siteId,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to create technician");
      }
      setNewName(""); setNewEmail(""); setNewPhone(""); setNewTelegram(""); setNewSpecs(["general"]);
      setShowAdd(false);
      await fetchData();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to create technician");
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (tech: Technician) => {
    setEditingId(tech.id);
    setEditName(tech.name);
    setEditEmail(tech.email);
    setEditPhone(tech.phone || "");
    setEditSpecs(tech.specialties || []);
  };

  const handleUpdate = async (techId: string) => {
    try {
      const res = await authorizedFetch(`/api/technicians/${techId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName.trim() || undefined,
          email: editEmail.trim() || undefined,
          phone: editPhone.trim() || undefined,
          specialties: editSpecs.length ? editSpecs : undefined,
          site_id: siteId,
        }),
      });
      if (!res.ok) throw new Error("Failed to update");
      setEditingId(null);
      await fetchData();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to update technician");
    }
  };

  const handleToggleActive = async (tech: Technician) => {
    const endpoint = tech.active ? "deactivate" : "reactivate";
    try {
      const res = await authorizedFetch(`/api/technicians/${tech.id}/${endpoint}`, { method: "POST" });
      if (!res.ok) throw new Error(`Failed to ${endpoint}`);
      await fetchData();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : `Failed to ${endpoint} technician`);
    }
  };

  const specColor = (spec: string) => {
    const map: Record<string, string> = {
      hvac: "var(--color-sentinel-blue)",
      electrical: "var(--color-sentinel-amber)",
      dali: "rgb(168, 85, 247)",
      fire: "var(--color-sentinel-red)",
      security: "var(--color-sentinel-green)",
      plumbing: "var(--color-sentinel-blue)",
      general: "var(--color-sentinel-text-secondary)",
    };
    return map[spec] || "var(--color-sentinel-text-secondary)";
  };

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <Users className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Team & Technicians</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Manage technicians, disciplines, and notification channels
              </p>
            </div>
          </div>
          {!readOnly && (
            <button type="button" onClick={() => setShowAdd(!showAdd)}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)" }}
            >
              <Plus className="h-3 w-3" />
              Add Technician
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
                <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="John Smith" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Email *</label>
                <input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="john@company.co.za" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Phone</label>
                <input type="tel" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="+27721234567" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Telegram ID</label>
                <input type="text" value={newTelegram} onChange={(e) => setNewTelegram(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="@username or numeric ID" />
              </div>
            </div>
            <div>
              <label className="block text-xs mb-1.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>Disciplines</label>
              <div className="flex flex-wrap gap-1.5">
                {specialties.map((s) => (
                  <button key={s.id} type="button" onClick={() => setNewSpecs(toggleSpec(newSpecs, s.id))}
                    className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                    style={{
                      background: newSpecs.includes(s.id) ? `${specColor(s.id)}20` : "transparent",
                      color: specColor(s.id),
                      border: `1px solid ${newSpecs.includes(s.id) ? specColor(s.id) : "var(--glass-border)"}`,
                    }}
                  >
                    {s.label}
                    {s.equipment_types.length > 0 && (
                      <span className="ml-1 opacity-50">({s.equipment_types.length})</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Cancel</button>
              <button type="button" onClick={() => void handleAdd()} disabled={adding || !newName.trim() || !newEmail.trim()}
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium"
                style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)", opacity: adding || !newName.trim() || !newEmail.trim() ? 0.5 : 1 }}
              >
                <Save className="h-3 w-3" />
                {adding ? "Adding..." : "Add Technician"}
              </button>
            </div>
          </div>
        )}

        {/* Technician List */}
        {loading ? (
          <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading technicians...</p>
        ) : technicians.length === 0 ? (
          <div className="text-center py-8">
            <Users className="h-8 w-8 mx-auto mb-2" style={{ color: "var(--color-sentinel-text-secondary)", opacity: 0.3 }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No technicians registered</p>
            <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Add your first technician to enable alert routing and work order assignment</p>
          </div>
        ) : (
          <div className="space-y-2">
            {technicians.map((tech) => {
              const isEditing = editingId === tech.id;

              return (
                <div key={tech.id} className="p-3 rounded-lg" style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--glass-border)",
                  opacity: tech.active ? 1 : 0.5,
                }}>
                  {isEditing ? (
                    /* Edit Mode */
                    <div className="space-y-2">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                        <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} placeholder="Name" />
                        <input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} placeholder="Email" />
                        <input type="tel" value={editPhone} onChange={(e) => setEditPhone(e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} placeholder="Phone" />
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {specialties.map((s) => (
                          <button key={s.id} type="button" onClick={() => setEditSpecs(toggleSpec(editSpecs, s.id))}
                            className="px-2 py-0.5 rounded text-[10px] font-medium"
                            style={{
                              background: editSpecs.includes(s.id) ? `${specColor(s.id)}20` : "transparent",
                              color: specColor(s.id),
                              border: `1px solid ${editSpecs.includes(s.id) ? specColor(s.id) : "var(--glass-border)"}`,
                            }}
                          >{s.label}</button>
                        ))}
                      </div>
                      <div className="flex justify-end gap-1">
                        <button type="button" onClick={() => setEditingId(null)} className="p-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          <X className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => void handleUpdate(tech.id)} className="p-1" style={{ color: "var(--color-sentinel-green)" }}>
                          <Save className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Display Mode */
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{tech.name}</span>
                          {!tech.active && <span className="text-[10px] px-1 py-0.5 rounded" style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}>inactive</span>}
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{tech.email}</span>
                          {tech.phone && <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{tech.phone}</span>}
                        </div>
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {(tech.specialties || []).map((s) => (
                            <span key={s} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${specColor(s)}15`, color: specColor(s) }}>{s}</span>
                          ))}
                          {tech.channels && tech.channels.map((ch) => (
                            <span key={ch.channel_type} className="text-[10px] px-1.5 py-0.5 rounded" style={{
                              background: ch.is_verified ? "rgba(16, 185, 129, 0.1)" : "rgba(245, 158, 11, 0.1)",
                              color: ch.is_verified ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
                            }}>
                              {ch.channel_type} {ch.is_verified ? "" : "(unverified)"}
                            </span>
                          ))}
                        </div>
                      </div>
                      {!readOnly && (
                        <div className="flex items-center gap-1">
                          <button type="button" onClick={() => startEdit(tech)} className="p-1" style={{ color: "var(--color-sentinel-blue)" }} title="Edit">
                            <Edit2 className="h-3.5 w-3.5" />
                          </button>
                          <button type="button" onClick={() => void handleToggleActive(tech)} className="p-1"
                            style={{ color: tech.active ? "var(--color-sentinel-red)" : "var(--color-sentinel-green)" }}
                            title={tech.active ? "Deactivate" : "Reactivate"}
                          >
                            {tech.active ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
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
