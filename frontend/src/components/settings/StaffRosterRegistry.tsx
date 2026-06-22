import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Database, Edit2, Plus, Save, Upload, UserX, Users, X } from "lucide-react";
import type {
  StaffRosterConnectorSettings,
  StaffRosterCreate,
  StaffRosterMember,
} from "../../lib/api";
import { staffRosterApi } from "../../lib/api";

interface StaffRosterRegistryProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

const EMPTY_MEMBER = (siteId: string): StaffRosterCreate => ({
  staff_number: "",
  name: "",
  email: "",
  phone: "",
  desk: "",
  site_id: siteId,
  active: true,
  source: "manual",
});

const DEFAULT_CONNECTOR: StaffRosterConnectorSettings = {
  enabled: false,
  source_type: "csv",
  endpoint_url: "",
  sync_cadence: "manual",
  last_sync_at: null,
  notes: "",
};

export function StaffRosterRegistry({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: StaffRosterRegistryProps) {
  const [members, setMembers] = useState<StaffRosterMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [newMember, setNewMember] = useState<StaffRosterCreate>(() => EMPTY_MEMBER(siteId));
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editMember, setEditMember] = useState<StaffRosterCreate>(() => EMPTY_MEMBER(siteId));
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [connector, setConnector] = useState<StaffRosterConnectorSettings>(DEFAULT_CONNECTOR);
  const [savingConnector, setSavingConnector] = useState(false);

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  const requiredReady = useMemo(
    () => Boolean(newMember.staff_number.trim() && newMember.name.trim() && newMember.email.trim() && newMember.phone.trim() && newMember.desk.trim()),
    [newMember],
  );

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [roster, connectorSettings] = await Promise.all([
        staffRosterApi.list(siteId),
        staffRosterApi.getConnector(),
      ]);
      setMembers(roster.members || []);
      setConnector({ ...DEFAULT_CONNECTOR, ...connectorSettings });
    } catch {
      onError?.("Failed to load staff roster");
    } finally {
      setLoading(false);
    }
  }, [siteId, onError]);

  useEffect(() => {
    setNewMember(EMPTY_MEMBER(siteId));
    void fetchAll();
  }, [siteId, fetchAll]);

  const updateNew = (field: keyof StaffRosterCreate, value: string) => {
    setNewMember((prev) => ({ ...prev, [field]: value }));
  };

  const updateEdit = (field: keyof StaffRosterCreate, value: string) => {
    setEditMember((prev) => ({ ...prev, [field]: value }));
  };

  const handleAdd = async () => {
    if (!requiredReady || readOnly) return;
    setAdding(true);
    try {
      await staffRosterApi.create({ ...newMember, site_id: siteId, source: "manual" });
      setNewMember(EMPTY_MEMBER(siteId));
      setShowAdd(false);
      await fetchAll();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to add staff member");
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (member: StaffRosterMember) => {
    setEditingId(member.id);
    setEditMember({
      staff_number: member.staff_number,
      name: member.name,
      email: member.email,
      phone: member.phone,
      desk: member.desk,
      site_id: member.site_id,
      active: member.active,
      source: member.source || "manual",
    });
  };

  const handleUpdate = async (memberId: string) => {
    if (readOnly) return;
    try {
      await staffRosterApi.update(memberId, editMember);
      setEditingId(null);
      await fetchAll();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to update staff member");
    }
  };

  const handleDeactivate = async (member: StaffRosterMember) => {
    if (readOnly || !confirm(`Deactivate ${member.name}?`)) return;
    try {
      await staffRosterApi.deactivate(member.id);
      await fetchAll();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to deactivate staff member");
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || readOnly) return;
    setUploading(true);
    setUploadMessage("");
    try {
      const result = await staffRosterApi.importCsv(selectedFile, siteId);
      setUploadMessage(`Imported ${result.imported} row${result.imported === 1 ? "" : "s"}${result.skipped ? `, skipped ${result.skipped}` : ""}`);
      setSelectedFile(null);
      await fetchAll();
      onSuccess?.();
      if (result.errors.length) onError?.(result.errors.slice(0, 3).join("; "));
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to upload staff roster");
    } finally {
      setUploading(false);
    }
  };

  const handleSaveConnector = async () => {
    if (readOnly) return;
    setSavingConnector(true);
    try {
      const saved = await staffRosterApi.updateConnector(connector);
      setConnector({ ...DEFAULT_CONNECTOR, ...saved });
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to save staff connector");
    } finally {
      setSavingConnector(false);
    }
  };

  const downloadTemplate = () => {
    const csv = "staff_number,name,email,phone,desk,site_id,active\nS002-001,Jane Staff,jane@example.com,+27721234567,Desk 208,site-002,true\n";
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "staff-roster-template.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(20, 184, 166, 0.15)", color: "rgb(20, 184, 166)" }}>
              <Users className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Staff Registry</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Roster for Sentry Staff bot registration and desk context</p>
            </div>
          </div>
          {!readOnly && (
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={downloadTemplate} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium" style={{ background: "rgba(59, 130, 246, 0.12)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
                <Database className="h-3 w-3" />
                Template
              </button>
              <button type="button" onClick={() => setShowAdd(!showAdd)} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                <Plus className="h-3 w-3" />
                Add Staff
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {!readOnly && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="p-4 rounded space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
              <div className="flex items-center gap-2">
                <Upload className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                <h3 className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>CSV Upload</h3>
              </div>
              <input type="file" accept=".csv,text/csv" onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)} className="w-full rounded px-3 py-2 text-xs" style={inputStyle} />
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>{selectedFile?.name || "staff_number,name,email,phone,desk"}</span>
                <button type="button" onClick={() => void handleUpload()} disabled={!selectedFile || uploading} className="px-3 py-1.5 rounded text-xs font-medium" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)", opacity: !selectedFile || uploading ? 0.5 : 1 }}>
                  {uploading ? "Uploading..." : "Upload"}
                </button>
              </div>
              {uploadMessage && <div className="flex items-center gap-1 text-xs" style={{ color: "var(--color-sentinel-green)" }}><CheckCircle2 className="h-3 w-3" />{uploadMessage}</div>}
            </div>

            <div className="p-4 rounded space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
                <h3 className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>HR Connector</h3>
              </div>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                <select value={connector.source_type} onChange={(e) => setConnector((prev) => ({ ...prev, source_type: e.target.value }))} className="rounded px-3 py-1.5 text-xs" style={inputStyle}>
                  <option value="csv">CSV drop</option>
                  <option value="hr_api">HR API</option>
                  <option value="database">Database view</option>
                  <option value="sftp">SFTP export</option>
                </select>
                <select value={connector.sync_cadence} onChange={(e) => setConnector((prev) => ({ ...prev, sync_cadence: e.target.value }))} className="rounded px-3 py-1.5 text-xs" style={inputStyle}>
                  <option value="manual">Manual</option>
                  <option value="hourly">Hourly</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                </select>
              </div>
              <input type="text" value={connector.endpoint_url || ""} onChange={(e) => setConnector((prev) => ({ ...prev, endpoint_url: e.target.value }))} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Connector URL, table, or SFTP path" />
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <input type="checkbox" checked={connector.enabled} onChange={(e) => setConnector((prev) => ({ ...prev, enabled: e.target.checked }))} />
                  Enabled
                </label>
                <button type="button" onClick={() => void handleSaveConnector()} disabled={savingConnector} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium" style={{ background: "rgba(245, 158, 11, 0.14)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245, 158, 11, 0.3)", opacity: savingConnector ? 0.5 : 1 }}>
                  <Save className="h-3 w-3" />
                  {savingConnector ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
          </div>
        )}

        {showAdd && !readOnly && (
          <div className="p-4 rounded space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <input value={newMember.staff_number} onChange={(e) => updateNew("staff_number", e.target.value)} className="rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Staff number" />
              <input value={newMember.name} onChange={(e) => updateNew("name", e.target.value)} className="rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Name" />
              <input type="email" value={newMember.email} onChange={(e) => updateNew("email", e.target.value)} className="rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Email" />
              <input value={newMember.phone} onChange={(e) => updateNew("phone", e.target.value)} className="rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Phone" />
              <input value={newMember.desk} onChange={(e) => updateNew("desk", e.target.value)} className="rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Desk" />
              <input value={siteId} readOnly className="rounded px-3 py-1.5 text-xs" style={{ ...inputStyle, opacity: 0.75 }} />
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Cancel</button>
              <button type="button" onClick={() => void handleAdd()} disabled={adding || !requiredReady} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)", opacity: adding || !requiredReady ? 0.5 : 1 }}>
                <Save className="h-3 w-3" />
                {adding ? "Adding..." : "Add Staff"}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading staff roster...</p>
        ) : members.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            <AlertCircle className="h-4 w-4" />
            No staff roster loaded
          </div>
        ) : (
          <div className="space-y-2">
            {members.map((member) => {
              const isEditing = editingId === member.id;
              return (
                <div key={member.id} className="p-3 rounded" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: member.active ? 1 : 0.55 }}>
                  {isEditing ? (
                    <div className="space-y-2">
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-5">
                        <input value={editMember.staff_number} onChange={(e) => updateEdit("staff_number", e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} />
                        <input value={editMember.name} onChange={(e) => updateEdit("name", e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} />
                        <input value={editMember.email} onChange={(e) => updateEdit("email", e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} />
                        <input value={editMember.phone} onChange={(e) => updateEdit("phone", e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} />
                        <input value={editMember.desk} onChange={(e) => updateEdit("desk", e.target.value)} className="rounded px-2 py-1 text-xs" style={inputStyle} />
                      </div>
                      <div className="flex justify-end gap-1">
                        <button type="button" onClick={() => setEditingId(null)} className="p-1" style={{ color: "var(--color-sentinel-text-secondary)" }}><X className="h-3.5 w-3.5" /></button>
                        <button type="button" onClick={() => void handleUpdate(member.id)} className="p-1" style={{ color: "var(--color-sentinel-green)" }}><Save className="h-3.5 w-3.5" /></button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{member.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(20, 184, 166, 0.12)", color: "rgb(20, 184, 166)" }}>{member.staff_number}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(59, 130, 246, 0.12)", color: "var(--color-sentinel-blue)" }}>{member.desk}</span>
                        </div>
                        <div className="flex flex-wrap gap-3 mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          <span>{member.email}</span>
                          <span>{member.phone}</span>
                          <span>{member.source}</span>
                        </div>
                      </div>
                      {!readOnly && (
                        <div className="flex items-center gap-1">
                          <button type="button" onClick={() => startEdit(member)} className="p-1" style={{ color: "var(--color-sentinel-blue)" }} title="Edit"><Edit2 className="h-3.5 w-3.5" /></button>
                          <button type="button" onClick={() => void handleDeactivate(member)} className="p-1" style={{ color: "var(--color-sentinel-red)" }} title="Deactivate"><UserX className="h-3.5 w-3.5" /></button>
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
