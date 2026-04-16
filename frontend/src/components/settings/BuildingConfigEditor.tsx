import { useState, useEffect, useCallback } from "react";
import { Building2, Save } from "lucide-react";
import { buildingConfigApi } from "../../lib/api";
import type { BuildingConfig } from "../../lib/api";

interface BuildingConfigEditorProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

const BUILDING_TYPES = [
  { value: "commercial_office", label: "Commercial Office" },
  { value: "retail", label: "Retail" },
  { value: "industrial", label: "Industrial" },
  { value: "mixed_use", label: "Mixed Use" },
  { value: "warehouse", label: "Warehouse" },
  { value: "data_center", label: "Data Center" },
];

const OPTIMIZATION_PROFILES = [
  { value: "cost_saving", label: "Cost Saving", desc: "Minimize energy spend" },
  { value: "comfort", label: "Comfort First", desc: "Prioritize occupant comfort" },
  { value: "balanced", label: "Balanced", desc: "Balance cost and comfort" },
];

const CONTROL_TIERS = [
  { value: "human_in_loop", label: "Human in Loop", desc: "All actions require approval" },
  { value: "supervised", label: "Supervised", desc: "Auto-act within safe bounds, escalate edge cases" },
  { value: "automatic", label: "Automatic", desc: "Full autonomy within safety envelope" },
];

function deriveSentinelOperatingMode(
  value?: string | null,
): "comfort" | "cost_saving" | "asset_preservation" {
  if (value === "cost_saving" || value === "comfort" || value === "asset_preservation") {
    return value;
  }
  if (value === "cost") return "cost_saving";
  if (value === "sweat_assets" || value === "asset_sweating") return "asset_preservation";
  return "comfort";
}

export function BuildingConfigEditor({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: BuildingConfigEditorProps) {
  const [config, setConfig] = useState<BuildingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Editable fields
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [address, setAddress] = useState("");
  const [buildingType, setBuildingType] = useState("");
  const [floors, setFloors] = useState("");
  const [sqm, setSqm] = useState("");
  const [occupancyCap, setOccupancyCap] = useState("");
  const [totalDesks, setTotalDesks] = useState("");
  const [parkingBays, setParkingBays] = useState("");
  const [optimizationProfile, setOptimizationProfile] = useState("");
  const [sentinelOperatingMode, setSentinelOperatingMode] = useState<"comfort" | "cost_saving" | "asset_preservation">("comfort");
  const [controlTier, setControlTier] = useState("");
  const [contactFM, setContactFM] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactEmergency, setContactEmergency] = useState("");

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const data = await buildingConfigApi.getConfig(siteId);
      setConfig(data);

      // Populate form
      setName(data.name || "");
      setDisplayName(data.display_name || "");
      setAddress(data.address || "");
      setBuildingType(data.type || "commercial_office");
      setFloors((data.floors || []).join(", "));
      setSqm(String(data.metadata?.sqm || ""));
      setOccupancyCap(String(data.metadata?.occupancy_capacity || ""));
      setTotalDesks(String(data.metadata?.total_desks || ""));
      setParkingBays(String(data.metadata?.parking_bays || ""));
      setOptimizationProfile(data.optimization?.active_profile || "balanced");
      setSentinelOperatingMode(
        deriveSentinelOperatingMode(data.optimization?.sentinel_operating_mode || data.optimization?.active_profile),
      );
      setControlTier(data.optimization?.control_tier || "human_in_loop");
      setContactFM(data.contacts?.facility_manager || "");
      setContactEmail(data.contacts?.email || "");
      setContactEmergency(data.contacts?.emergency || "");
      setDirty(false);
    } catch {
      onError?.("Failed to load building configuration");
    } finally {
      setLoading(false);
    }
  }, [siteId, onError]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const markDirty = () => setDirty(true);

  const handleSave = async () => {
    if (readOnly || !dirty) return;
    setSaving(true);
    try {
      const floorsArray = floors
        .split(",")
        .map((f) => f.trim())
        .filter(Boolean);

      await buildingConfigApi.updateConfig(siteId, {
        name: name || undefined,
        display_name: displayName || undefined,
        address: address || undefined,
        building_type: buildingType || undefined,
        floors: floorsArray.length ? floorsArray : undefined,
        sqm: sqm ? parseInt(sqm, 10) : undefined,
        occupancy_capacity: occupancyCap ? parseInt(occupancyCap, 10) : undefined,
        total_desks: totalDesks ? parseInt(totalDesks, 10) : undefined,
        parking_bays: parkingBays ? parseInt(parkingBays, 10) : undefined,
        optimization_profile: optimizationProfile || undefined,
        sentinel_operating_mode: sentinelOperatingMode,
        control_tier: controlTier || undefined,
        contacts: {
          facility_manager: contactFM || undefined,
          email: contactEmail || undefined,
          emergency: contactEmergency || undefined,
        },
      });
      setDirty(false);
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to save building config");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="glass-panel overflow-hidden">
        <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Building Profile</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!config) return null;

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  const labelStyle = { color: "var(--color-sentinel-text-secondary)" };

  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Building Profile</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Building metadata, optimization, and contact details
              </p>
            </div>
          </div>
          {!readOnly && dirty && (
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving}
              className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
              style={{
                background: "rgba(59, 130, 246, 0.15)",
                color: "var(--color-sentinel-blue)",
                border: "1px solid rgba(59, 130, 246, 0.3)",
                opacity: saving ? 0.6 : 1,
              }}
            >
              <Save className="h-4 w-4" />
              {saving ? "Saving..." : "Save Changes"}
            </button>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Basic Information */}
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Basic Information</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => { setName(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => { setDisplayName(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs mb-1" style={labelStyle}>Address</label>
              <input
                type="text"
                value={address}
                onChange={(e) => { setAddress(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Building Type</label>
              <select
                value={buildingType}
                onChange={(e) => { setBuildingType(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              >
                {BUILDING_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Floors (comma-separated)</label>
              <input
                type="text"
                value={floors}
                onChange={(e) => { setFloors(e.target.value); markDirty(); }}
                disabled={readOnly}
                placeholder="B1, L1, L2, L3, Roof"
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
          </div>
        </div>

        {/* Metrics */}
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Building Metrics</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>GFA (sqm)</label>
              <input
                type="number"
                value={sqm}
                onChange={(e) => { setSqm(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Occupancy Capacity</label>
              <input
                type="number"
                value={occupancyCap}
                onChange={(e) => { setOccupancyCap(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Total Desks</label>
              <input
                type="number"
                value={totalDesks}
                onChange={(e) => { setTotalDesks(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Parking Bays</label>
              <input
                type="number"
                value={parkingBays}
                onChange={(e) => { setParkingBays(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
          </div>
        </div>

        {/* Optimization Profile */}
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Optimization Profile</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {OPTIMIZATION_PROFILES.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => { if (!readOnly) { setOptimizationProfile(p.value); markDirty(); } }}
                disabled={readOnly}
                className="p-3 rounded-lg text-left transition-colors"
                style={{
                  background: optimizationProfile === p.value
                    ? "rgba(59, 130, 246, 0.15)"
                    : "var(--color-sentinel-bg-secondary)",
                  border: `1px solid ${optimizationProfile === p.value ? "rgba(59, 130, 246, 0.4)" : "var(--glass-border)"}`,
                  cursor: readOnly ? "not-allowed" : "pointer",
                }}
              >
                <div className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{p.label}</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>{p.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Control Tier */}
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Control Tier</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {CONTROL_TIERS.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => { if (!readOnly) { setControlTier(t.value); markDirty(); } }}
                disabled={readOnly}
                className="p-3 rounded-lg text-left transition-colors"
                style={{
                  background: controlTier === t.value
                    ? "rgba(16, 185, 129, 0.15)"
                    : "var(--color-sentinel-bg-secondary)",
                  border: `1px solid ${controlTier === t.value ? "rgba(16, 185, 129, 0.4)" : "var(--glass-border)"}`,
                  cursor: readOnly ? "not-allowed" : "pointer",
                }}
              >
                <div className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{t.label}</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>{t.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Contacts */}
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>Contacts</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Facility Manager</label>
              <input
                type="text"
                value={contactFM}
                onChange={(e) => { setContactFM(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Email</label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => { setContactEmail(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={labelStyle}>Emergency Phone</label>
              <input
                type="tel"
                value={contactEmergency}
                onChange={(e) => { setContactEmergency(e.target.value); markDirty(); }}
                disabled={readOnly}
                className="w-full rounded px-3 py-2 text-sm"
                style={inputStyle}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
