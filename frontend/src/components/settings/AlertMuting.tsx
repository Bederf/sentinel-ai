import { useState, useEffect, useCallback } from "react";
import { VolumeX, Volume2, Plus } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface AlertMute {
  id: string;
  equipment_code: string;
  reason: string;
  duration_hours: number;
  muted_at: string;
  muted_until: string;
  muted_by: string;
}

interface AlertMutingProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

export function AlertMuting({ siteId, onError, onSuccess, readOnly = false }: AlertMutingProps) {
  const [mutes, setMutes] = useState<AlertMute[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newReason, setNewReason] = useState("");
  const [newDuration, setNewDuration] = useState("24");

  const fetchMutes = useCallback(async () => {
    setLoading(true);
    try {
      const query = siteId ? `?site_id=${encodeURIComponent(siteId)}` : "";
      const response = await authorizedFetch(`/api/alert-muting${query}`);
      if (!response.ok) throw new Error("Failed to fetch mutes");
      const data = await response.json();
      setMutes(data.mutes || []);
    } catch {
      onError?.("Failed to load active mutes");
    } finally {
      setLoading(false);
    }
  }, [onError, siteId]);

  useEffect(() => { fetchMutes(); }, [fetchMutes]);

  const handleMute = async () => {
    if (!newCode.trim() || !newReason.trim()) return;
    try {
      const response = await authorizedFetch(`/api/alert-muting/${encodeURIComponent(newCode.trim())}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: newReason.trim(), duration_hours: parseInt(newDuration) || 24 }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to mute equipment");
      }
      setNewCode(""); setNewReason(""); setNewDuration("24"); setShowAdd(false);
      await fetchMutes();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to mute equipment");
    }
  };

  const handleUnmute = async (code: string) => {
    try {
      const response = await authorizedFetch(`/api/alert-muting/${encodeURIComponent(code)}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Failed to unmute");
      await fetchMutes();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to unmute equipment");
    }
  };

  const timeRemaining = (until: string) => {
    const ms = new Date(until).getTime() - Date.now();
    if (ms <= 0) return "expired";
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
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
            <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
              <VolumeX className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Equipment Muting</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Suppress alerts for specific equipment during maintenance
              </p>
            </div>
          </div>
          {!readOnly && (
            <button type="button" onClick={() => setShowAdd(!showAdd)}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245, 158, 11, 0.3)" }}
            >
              <Plus className="h-3 w-3" />
              Mute Equipment
            </button>
          )}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {showAdd && !readOnly && (
          <div className="p-3 rounded-lg space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Equipment Code</label>
                <input type="text" value={newCode} onChange={(e) => setNewCode(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="S002-CHILLER-B1-001" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Reason</label>
                <input type="text" value={newReason} onChange={(e) => setNewReason(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} placeholder="Scheduled maintenance" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Duration (hours)</label>
                <input type="number" value={newDuration} onChange={(e) => setNewDuration(e.target.value)} className="w-full rounded px-3 py-1.5 text-xs" style={inputStyle} min={1} max={720} />
              </div>
              <div className="flex items-end">
                <button type="button" onClick={() => void handleMute()} disabled={!newCode.trim() || !newReason.trim()}
                  className="px-3 py-1.5 rounded text-xs font-medium"
                  style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)", border: "1px solid rgba(245, 158, 11, 0.3)", opacity: !newCode.trim() || !newReason.trim() ? 0.5 : 1 }}
                >Mute</button>
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading...</p>
        ) : mutes.length === 0 ? (
          <div className="text-center py-4">
            <Volume2 className="h-6 w-6 mx-auto mb-2" style={{ color: "var(--color-sentinel-green)" }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No equipment currently muted</p>
          </div>
        ) : (
          mutes.map((mute) => (
            <div key={mute.id} className="flex items-center justify-between p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-medium" style={{ color: "var(--color-sentinel-amber)" }}>{mute.equipment_code}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
                    {timeRemaining(mute.muted_until)} remaining
                  </span>
                </div>
                <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {mute.reason} — by {mute.muted_by}
                </p>
              </div>
              {!readOnly && (
                <button type="button" onClick={() => void handleUnmute(mute.equipment_code)}
                  className="px-2 py-1 rounded text-xs font-medium transition-colors hover:brightness-110"
                  style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)" }}
                >Unmute</button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
