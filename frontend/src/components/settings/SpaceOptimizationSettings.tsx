/**
 * Space Optimization Settings component.
 *
 * Provides grace period configuration and concierge user CRUD management.
 * Phase 155: Ghost booking detection, room right-sizing, focus room analytics.
 */

import { useState, useEffect, useCallback } from "react";
import { Users, Clock, Plus, Pencil, Trash2, Check, X, ChevronDown } from "lucide-react";
import type {
  SpaceGracePeriods,
  ConciergeUser,
  ConciergeUserCreate,
  ConciergeUserUpdate,
  SpaceSiteStructure,
} from "../../lib/api";
import { spaceSettingsApi } from "../../lib/api";

// ---------------------------------------------------------------------------
// Grace period field metadata
// ---------------------------------------------------------------------------

interface GraceField {
  key: keyof SpaceGracePeriods;
  label: string;
  help: string;
  unit: string;
  min: number;
  max: number;
  default: number;
}

const GRACE_FIELDS: GraceField[] = [
  {
    key: "ghost_booking_grace_minutes",
    label: "Ghost Booking Grace Period",
    help: "Minutes after a booking starts before flagging it as a ghost (no occupancy detected).",
    unit: "min",
    min: 1,
    max: 60,
    default: 15,
  },
  {
    key: "concierge_response_window_minutes",
    label: "Concierge Response Window",
    help: "Time allowed for a concierge to confirm room status after a ghost alert.",
    unit: "min",
    min: 5,
    max: 60,
    default: 15,
  },
  {
    key: "sensor_silence_threshold_minutes",
    label: "Sensor Silence Threshold",
    help: "Minutes without sensor data before treating the room as unoccupied.",
    unit: "min",
    min: 5,
    max: 120,
    default: 30,
  },
  {
    key: "right_sizing_grace_minutes",
    label: "Right-Sizing Grace Period",
    help: "Wait time before suggesting a smaller room when occupancy is significantly below capacity.",
    unit: "min",
    min: 5,
    max: 60,
    default: 20,
  },
  {
    key: "early_vacate_threshold_minutes",
    label: "Early Vacate Threshold",
    help: "Minutes before booking end that triggers an early-vacate event if room empties.",
    unit: "min",
    min: 30,
    max: 180,
    default: 90,
  },
  {
    key: "sporadic_use_threshold_pct",
    label: "Sporadic Use Threshold",
    help: "Percentage of booked time with occupancy below which usage is flagged as sporadic.",
    unit: "%",
    min: 5,
    max: 75,
    default: 25,
  },
  {
    key: "brief_occupation_threshold_min",
    label: "Brief Occupation Threshold",
    help: "Minimum continuous occupancy (minutes) to count as genuine use, not a walk-through.",
    unit: "min",
    min: 10,
    max: 120,
    default: 30,
  },
];

// ---------------------------------------------------------------------------
// Empty concierge form data
// ---------------------------------------------------------------------------

function emptyConciergeForm(siteId?: string): ConciergeUserCreate {
  return {
    name: "",
    mobile: "",
    email: "",
    site_id: siteId || "",
    building_codes: [],
    floor_assignments: {},
  };
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SpaceOptimizationSettingsProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SpaceOptimizationSettings({
  siteId,
  onError,
  onSuccess,
  readOnly = false,
}: SpaceOptimizationSettingsProps) {
  // Grace period state
  const [graceValues, setGraceValues] = useState<SpaceGracePeriods>(() => {
    const defaults: SpaceGracePeriods = {} as SpaceGracePeriods;
    for (const f of GRACE_FIELDS) {
      (defaults as unknown as Record<string, number>)[f.key] = f.default;
    }
    return defaults;
  });
  const [graceSaving, setGraceSaving] = useState(false);

  // Concierge state
  const [concierges, setConcierges] = useState<ConciergeUser[]>([]);
  const [sites, setSites] = useState<SpaceSiteStructure[]>([]);
  const [loading, setLoading] = useState(true);

  // Inline form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<ConciergeUserCreate>(emptyConciergeForm());
  const [formActive, setFormActive] = useState(true);
  const [formSaving, setFormSaving] = useState(false);

  // Delete confirmation
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Pre-seed form site from the current site context when siteId prop is set
  useEffect(() => {
    if (siteId) {
      setFormData((prev) => ({ ...prev, site_id: siteId }));
    }
  }, [siteId]);

  // -------------------------------------------
  // Fetch on mount
  // -------------------------------------------
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [settings, sitesData] = await Promise.all([
        spaceSettingsApi.getSettings(),
        spaceSettingsApi.getSites(),
      ]);
      const gp: SpaceGracePeriods = {} as SpaceGracePeriods;
      for (const f of GRACE_FIELDS) {
        (gp as unknown as Record<string, number>)[f.key] =
          (settings as unknown as Record<string, number>)[f.key] ?? f.default;
      }
      setGraceValues(gp);
      setConcierges(settings.concierges || []);
      setSites(sitesData);
    } catch {
      onError?.("Failed to load space optimization settings");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // -------------------------------------------
  // Grace period handlers
  // -------------------------------------------
  const handleGraceChange = (key: keyof SpaceGracePeriods, value: number) => {
    setGraceValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleGraceSave = async () => {
    if (readOnly) return;
    setGraceSaving(true);
    try {
      const updated = await spaceSettingsApi.updateSettings(graceValues);
      setConcierges(updated.concierges || []);
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to save grace period settings");
    } finally {
      setGraceSaving(false);
    }
  };

  // -------------------------------------------
  // Concierge form helpers
  // -------------------------------------------
  const selectedSite = sites.find((s) => s.site_id === formData.site_id);

  const toggleBuilding = (code: string) => {
    setFormData((prev) => {
      const codes = prev.building_codes.includes(code)
        ? prev.building_codes.filter((c) => c !== code)
        : [...prev.building_codes, code];
      // Remove floor assignments for deselected buildings
      const floors = { ...prev.floor_assignments };
      for (const k of Object.keys(floors)) {
        if (!codes.includes(k)) delete floors[k];
      }
      return { ...prev, building_codes: codes, floor_assignments: floors };
    });
  };

  const toggleFloor = (buildingCode: string, floor: number) => {
    setFormData((prev) => {
      const current = prev.floor_assignments[buildingCode] || [];
      const updated = current.includes(floor)
        ? current.filter((f) => f !== floor)
        : [...current, floor].sort((a, b) => a - b);
      return {
        ...prev,
        floor_assignments: { ...prev.floor_assignments, [buildingCode]: updated },
      };
    });
  };

  const startAdd = () => {
    setEditingId(null);
    setFormData(emptyConciergeForm(siteId));
    setFormActive(true);
    setShowAddForm(true);
  };

  const startEdit = (c: ConciergeUser) => {
    setShowAddForm(false);
    setEditingId(c.id);
    setFormData({
      name: c.name,
      mobile: c.mobile,
      email: c.email,
      site_id: c.site_id,
      building_codes: [...c.building_codes],
      floor_assignments: JSON.parse(JSON.stringify(c.floor_assignments)),
    });
    setFormActive(c.active);
  };

  const cancelForm = () => {
    setShowAddForm(false);
    setEditingId(null);
    setFormData(emptyConciergeForm());
  };

  const handleFormSave = async () => {
    if (readOnly) return;
    if (!formData.name.trim()) {
      onError?.("Concierge name is required");
      return;
    }
    if (!formData.site_id) {
      onError?.("Please select a site");
      return;
    }

    setFormSaving(true);
    try {
      if (editingId) {
        const updatePayload: ConciergeUserUpdate = { ...formData, active: formActive };
        const updated = await spaceSettingsApi.updateConcierge(editingId, updatePayload);
        setConcierges((prev) => prev.map((c) => (c.id === editingId ? updated : c)));
      } else {
        const created = await spaceSettingsApi.createConcierge(formData);
        setConcierges((prev) => [...prev, created]);
      }
      cancelForm();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to save concierge");
    } finally {
      setFormSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (readOnly) return;
    try {
      await spaceSettingsApi.deleteConcierge(id);
      setConcierges((prev) => prev.filter((c) => c.id !== id));
      setDeletingId(null);
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to delete concierge");
    }
  };

  // -------------------------------------------
  // Render helpers
  // -------------------------------------------
  const siteName = (siteId: string) =>
    sites.find((s) => s.site_id === siteId)?.site_name || siteId;

  if (loading) {
    return (
      <div className="glass-panel overflow-hidden">
        <div className="p-6 flex items-center justify-center">
          <div
            className="animate-spin h-6 w-6 border-4 rounded-full"
            style={{
              borderColor: "var(--color-sentinel-blue)",
              borderTopColor: "transparent",
            }}
          />
          <span
            className="ml-3 text-sm"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Loading space settings...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Section A: Grace Period Settings */}
      <div className="glass-panel overflow-hidden">
        <div
          className="p-4 border-b"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{
                background: "rgba(59, 130, 246, 0.15)",
                color: "var(--color-sentinel-blue)",
              }}
            >
              <Clock className="h-5 w-5" />
            </div>
            <div>
              <h2
                className="text-lg font-semibold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Ghost Booking Detection
              </h2>
              <p
                className="text-sm"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Configure timing thresholds for ghost booking detection and room
                usage analysis
              </p>
            </div>
          </div>
        </div>

        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {GRACE_FIELDS.map((field) => (
              <div key={field.key} className="space-y-1.5">
                <label
                  className="block text-sm font-medium"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {field.label}
                </label>
                <p
                  className="text-xs leading-snug"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {field.help}
                </p>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={field.min}
                    max={field.max}
                    value={graceValues[field.key]}
                    disabled={readOnly}
                    onChange={(e) =>
                      handleGraceChange(
                        field.key,
                        Math.max(
                          field.min,
                          Math.min(field.max, Number(e.target.value) || field.min)
                        )
                      )
                    }
                    className="w-24 px-3 py-1.5 rounded text-sm"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                      color: "var(--color-sentinel-text-primary)",
                    }}
                  />
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {field.unit} ({field.min}-{field.max})
                  </span>
                </div>
              </div>
            ))}
          </div>

          {!readOnly && (
            <div className="mt-6 flex justify-end">
              <button
                onClick={handleGraceSave}
                disabled={graceSaving}
                className="px-4 py-2 rounded text-sm font-medium transition-colors hover:brightness-110 disabled:opacity-50"
                style={{
                  background: "var(--color-sentinel-blue)",
                  color: "white",
                }}
              >
                {graceSaving ? "Saving..." : "Save Grace Periods"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Section B: Concierge Management */}
      <div className="glass-panel overflow-hidden">
        <div
          className="p-4 border-b"
          style={{ borderColor: "var(--color-sentinel-border)" }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{
                  background: "rgba(168, 85, 247, 0.15)",
                  color: "var(--color-sentinel-purple)",
                }}
              >
                <Users className="h-5 w-5" />
              </div>
              <div>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Concierge Users
                </h2>
                <p
                  className="text-sm"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Manage users who receive ghost booking alerts and confirm room
                  status
                </p>
              </div>
            </div>
            {!readOnly && !showAddForm && !editingId && (
              <button
                onClick={startAdd}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110"
                style={{
                  background: "rgba(16, 185, 129, 0.15)",
                  color: "var(--color-sentinel-green)",
                  border: "1px solid rgba(16, 185, 129, 0.3)",
                }}
              >
                <Plus className="h-4 w-4" />
                Add Concierge
              </button>
            )}
          </div>
        </div>

        <div className="p-4">
          {/* Add form */}
          {showAddForm && (
            <ConciergeForm
              title="New Concierge"
              formData={formData}
              formActive={formActive}
              sites={sites}
              selectedSite={selectedSite}
              saving={formSaving}
              isEdit={false}
              readonlySiteId={siteId}
              onChange={setFormData}
              onActiveChange={setFormActive}
              onToggleBuilding={toggleBuilding}
              onToggleFloor={toggleFloor}
              onSave={handleFormSave}
              onCancel={cancelForm}
            />
          )}

          {/* Table */}
          {concierges.length === 0 && !showAddForm ? (
            <div
              className="py-8 text-center text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {readOnly
                ? "No concierge users configured. Unlock settings to add one."
                : 'No concierge users configured. Click "Add Concierge" to create one.'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    {["Name", "Mobile", "Email", "Site", "Buildings / Floors", "Active", ""].map(
                      (h) => (
                        <th
                          key={h}
                          className="text-left py-2 px-3 font-medium text-xs uppercase tracking-wider"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {concierges.map((c) =>
                    editingId === c.id ? (
                      <tr key={c.id}>
                        <td colSpan={7} className="p-0">
                          <ConciergeForm
                            title="Edit Concierge"
                            formData={formData}
                            formActive={formActive}
                            sites={sites}
                            selectedSite={selectedSite}
                            saving={formSaving}
                            isEdit
                            readonlySiteId={siteId}
                            onChange={setFormData}
                            onActiveChange={setFormActive}
                            onToggleBuilding={toggleBuilding}
                            onToggleFloor={toggleFloor}
                            onSave={handleFormSave}
                            onCancel={cancelForm}
                          />
                        </td>
                      </tr>
                    ) : (
                      <tr
                        key={c.id}
                        style={{
                          borderBottom: "1px solid var(--color-sentinel-border)",
                        }}
                      >
                        <td
                          className="py-2 px-3"
                          style={{ color: "var(--color-sentinel-text-primary)" }}
                        >
                          {c.name}
                        </td>
                        <td
                          className="py-2 px-3"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {c.mobile}
                        </td>
                        <td
                          className="py-2 px-3"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {c.email}
                        </td>
                        <td
                          className="py-2 px-3"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {siteName(c.site_id)}
                        </td>
                        <td
                          className="py-2 px-3"
                          style={{ color: "var(--color-sentinel-text-secondary)" }}
                        >
                          {c.building_codes.length > 0
                            ? c.building_codes
                                .map((bc) => {
                                  const floors = c.floor_assignments[bc];
                                  return floors && floors.length > 0
                                    ? `${bc} (F${floors.join(",")})`
                                    : bc;
                                })
                                .join(", ")
                            : "All"}
                        </td>
                        <td className="py-2 px-3">
                          <span
                            className="inline-block h-2 w-2 rounded-full"
                            style={{
                              background: c.active
                                ? "var(--color-sentinel-green)"
                                : "var(--color-sentinel-red)",
                            }}
                          />
                        </td>
                        <td className="py-2 px-3">
                          {!readOnly && (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => startEdit(c)}
                                className="p-1 rounded hover:brightness-125 transition-colors"
                                style={{ color: "var(--color-sentinel-blue)" }}
                                title="Edit"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                              {deletingId === c.id ? (
                                <div className="flex items-center gap-1">
                                  <button
                                    onClick={() => handleDelete(c.id)}
                                    className="p-1 rounded hover:brightness-125 transition-colors"
                                    style={{ color: "var(--color-sentinel-red)" }}
                                    title="Confirm delete"
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    onClick={() => setDeletingId(null)}
                                    className="p-1 rounded hover:brightness-125 transition-colors"
                                    style={{
                                      color: "var(--color-sentinel-text-secondary)",
                                    }}
                                    title="Cancel"
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              ) : (
                                <button
                                  onClick={() => setDeletingId(c.id)}
                                  className="p-1 rounded hover:brightness-125 transition-colors"
                                  style={{ color: "var(--color-sentinel-red)" }}
                                  title="Delete"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline Concierge Form (shared by add + edit)
// ---------------------------------------------------------------------------

interface ConciergeFormProps {
  title: string;
  formData: ConciergeUserCreate;
  formActive: boolean;
  sites: SpaceSiteStructure[];
  selectedSite: SpaceSiteStructure | undefined;
  saving: boolean;
  isEdit: boolean;
  readonlySiteId?: string;
  onChange: (data: ConciergeUserCreate) => void;
  onActiveChange: (active: boolean) => void;
  onToggleBuilding: (code: string) => void;
  onToggleFloor: (buildingCode: string, floor: number) => void;
  onSave: () => void;
  onCancel: () => void;
}

function ConciergeForm({
  title,
  formData,
  formActive,
  sites,
  selectedSite,
  saving,
  isEdit,
  readonlySiteId,
  onChange,
  onActiveChange,
  onToggleBuilding,
  onToggleFloor,
  onSave,
  onCancel,
}: ConciergeFormProps) {
  const setField = (key: keyof ConciergeUserCreate, value: string) => {
    onChange({ ...formData, [key]: value });
  };

  // When site changes, reset building/floor selections
  const handleSiteChange = (siteId: string) => {
    onChange({
      ...formData,
      site_id: siteId,
      building_codes: [],
      floor_assignments: {},
    });
  };

  return (
    <div
      className="p-4 mb-4 rounded-lg space-y-4"
      style={{
        background: "var(--color-sentinel-bg-secondary)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <h3
        className="text-sm font-semibold"
        style={{ color: "var(--color-sentinel-text-primary)" }}
      >
        {title}
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Name */}
        <div className="space-y-1">
          <label
            className="block text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Name *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => setField("name", e.target.value)}
            placeholder="Jane Doe"
            className="w-full px-3 py-1.5 rounded text-sm"
            style={{
              background: "var(--color-sentinel-bg-canvas)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
        </div>

        {/* Mobile */}
        <div className="space-y-1">
          <label
            className="block text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Mobile
          </label>
          <input
            type="text"
            value={formData.mobile}
            onChange={(e) => setField("mobile", e.target.value)}
            placeholder="+27..."
            className="w-full px-3 py-1.5 rounded text-sm"
            style={{
              background: "var(--color-sentinel-bg-canvas)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
        </div>

        {/* Email */}
        <div className="space-y-1">
          <label
            className="block text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Email
          </label>
          <input
            type="email"
            value={formData.email}
            onChange={(e) => setField("email", e.target.value)}
            placeholder="jane@example.com"
            className="w-full px-3 py-1.5 rounded text-sm"
            style={{
              background: "var(--color-sentinel-bg-canvas)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          />
        </div>
      </div>

      {/* Site selection */}
      <div className="space-y-1">
        <label
          className="block text-xs font-medium"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Site {!readonlySiteId && "*"}
        </label>
        {readonlySiteId ? (
          <div
            className="px-3 py-1.5 rounded text-sm"
            style={{
              background: "var(--color-sentinel-bg-canvas)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            {selectedSite?.site_name || readonlySiteId}
          </div>
        ) : (
          <div className="relative w-full md:w-64">
            <select
              value={formData.site_id}
              onChange={(e) => handleSiteChange(e.target.value)}
              className="w-full appearance-none px-3 py-1.5 pr-8 rounded text-sm"
              style={{
                background: "var(--color-sentinel-bg-canvas)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <option value="">Select site...</option>
              {sites.map((s) => (
                <option key={s.site_id} value={s.site_id}>
                  {s.site_name}
                </option>
              ))}
            </select>
            <ChevronDown
              className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 pointer-events-none"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
          </div>
        )}
      </div>

      {/* Building checkboxes */}
      {selectedSite && selectedSite.buildings.length > 0 && (
        <div className="space-y-2">
          <label
            className="block text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Buildings
          </label>
          <div className="flex flex-wrap gap-3">
            {selectedSite.buildings.map((b) => (
              <label
                key={b.code}
                className="flex items-center gap-1.5 text-sm cursor-pointer"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                <input
                  type="checkbox"
                  checked={formData.building_codes.includes(b.code)}
                  onChange={() => onToggleBuilding(b.code)}
                  className="rounded"
                />
                {b.name || b.code}
              </label>
            ))}
          </div>

          {/* Floor checkboxes per selected building */}
          {formData.building_codes.map((bc) => {
            const building = selectedSite.buildings.find((b) => b.code === bc);
            if (!building || building.floors.length === 0) return null;
            return (
              <div key={bc} className="ml-4 space-y-1">
                <span
                  className="text-xs font-medium"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {building.name || bc} — Floors:
                </span>
                <div className="flex flex-wrap gap-2">
                  {building.floors.map((fl) => (
                    <label
                      key={fl}
                      className="flex items-center gap-1 text-xs cursor-pointer"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      <input
                        type="checkbox"
                        checked={(formData.floor_assignments[bc] || []).includes(fl)}
                        onChange={() => onToggleFloor(bc, fl)}
                        className="rounded"
                      />
                      F{fl}
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Active toggle (edit only) */}
      {isEdit && (
        <label
          className="flex items-center gap-2 text-sm cursor-pointer"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          <input
            type="checkbox"
            checked={formActive}
            onChange={(e) => onActiveChange(e.target.checked)}
            className="rounded"
          />
          Active
        </label>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110 disabled:opacity-50"
          style={{
            background: "var(--color-sentinel-blue)",
            color: "white",
          }}
        >
          <Check className="h-4 w-4" />
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          onClick={onCancel}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors hover:brightness-110"
          style={{
            background: "transparent",
            color: "var(--color-sentinel-text-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <X className="h-4 w-4" />
          Cancel
        </button>
      </div>
    </div>
  );
}
