import { useState, useEffect, useCallback } from "react";
import { Clock, Save } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface DaySchedule {
  start_time: string;
  end_time: string;
  pre_cool_minutes: number;
  is_operational: boolean;
}

type WeekSchedule = Record<string, DaySchedule>;

const DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const DAY_LABELS: Record<string, string> = {
  monday: "Mon", tuesday: "Tue", wednesday: "Wed", thursday: "Thu",
  friday: "Fri", saturday: "Sat", sunday: "Sun",
};

const DEFAULT_DAY: DaySchedule = { start_time: "06:00", end_time: "18:00", pre_cool_minutes: 60, is_operational: true };
const DEFAULT_WEEKEND: DaySchedule = { start_time: "00:00", end_time: "00:00", pre_cool_minutes: 0, is_operational: false };

interface OperatingScheduleEditorProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

export function OperatingScheduleEditor({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: OperatingScheduleEditorProps) {
  const [schedule, setSchedule] = useState<WeekSchedule>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const fetchSchedule = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authorizedFetch(`/api/buildings/${siteId}/schedule`);
      if (!response.ok) throw new Error("Failed to fetch schedule");
      const data = await response.json();
      setSchedule(data.schedule || {});
    } catch {
      onError?.("Failed to load operating schedule");
      // Set defaults
      const defaults: WeekSchedule = {};
      for (const day of DAY_ORDER) {
        defaults[day] = day === "saturday" || day === "sunday" ? { ...DEFAULT_WEEKEND } : { ...DEFAULT_DAY };
      }
      setSchedule(defaults);
    } finally {
      setLoading(false);
    }
  }, [siteId, onError]);

  useEffect(() => { fetchSchedule(); }, [fetchSchedule]);

  const updateDay = (day: string, field: keyof DaySchedule, value: string | number | boolean) => {
    setSchedule((prev) => ({
      ...prev,
      [day]: { ...(prev[day] || DEFAULT_DAY), [field]: value },
    }));
    setDirty(true);
  };

  const handleSave = async () => {
    if (readOnly || !dirty) return;
    setSaving(true);
    try {
      const response = await authorizedFetch(`/api/buildings/${siteId}/schedule`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(schedule),
      });
      if (!response.ok) throw new Error("Failed to save schedule");
      setDirty(false);
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to save schedule");
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  if (loading) {
    return (
      <div className="glass-panel flat overflow-hidden">
        <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <Clock className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Operating Hours</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <Clock className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Operating Hours</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Per-day operating schedule with pre-cool offsets
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
              {saving ? "Saving..." : "Save"}
            </button>
          )}
        </div>
      </div>

      <div className="p-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <th className="text-left py-2 px-2 text-xs font-medium">Day</th>
                <th className="text-left py-2 px-2 text-xs font-medium">Operational</th>
                <th className="text-left py-2 px-2 text-xs font-medium">Start</th>
                <th className="text-left py-2 px-2 text-xs font-medium">End</th>
                <th className="text-left py-2 px-2 text-xs font-medium">Pre-cool (min)</th>
              </tr>
            </thead>
            <tbody>
              {DAY_ORDER.map((day) => {
                const ds = schedule[day] || (day === "saturday" || day === "sunday" ? DEFAULT_WEEKEND : DEFAULT_DAY);
                return (
                  <tr key={day} className="border-t" style={{ borderColor: "var(--glass-border)" }}>
                    <td className="py-2 px-2 font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {DAY_LABELS[day]}
                    </td>
                    <td className="py-2 px-2">
                      <button
                        type="button"
                        onClick={() => !readOnly && updateDay(day, "is_operational", !ds.is_operational)}
                        disabled={readOnly}
                        className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
                        style={{
                          background: ds.is_operational ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
                          border: `1px solid ${ds.is_operational ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
                          cursor: readOnly ? "not-allowed" : "pointer",
                        }}
                      >
                        <span className="inline-block h-3 w-3 rounded-full bg-white transition-transform" style={{ transform: ds.is_operational ? "translateX(17px)" : "translateX(2px)" }} />
                      </button>
                    </td>
                    <td className="py-2 px-2">
                      <input
                        type="time"
                        value={ds.start_time}
                        onChange={(e) => updateDay(day, "start_time", e.target.value)}
                        disabled={readOnly || !ds.is_operational}
                        className="rounded px-2 py-1 text-xs w-24"
                        style={{ ...inputStyle, opacity: ds.is_operational ? 1 : 0.4 }}
                      />
                    </td>
                    <td className="py-2 px-2">
                      <input
                        type="time"
                        value={ds.end_time}
                        onChange={(e) => updateDay(day, "end_time", e.target.value)}
                        disabled={readOnly || !ds.is_operational}
                        className="rounded px-2 py-1 text-xs w-24"
                        style={{ ...inputStyle, opacity: ds.is_operational ? 1 : 0.4 }}
                      />
                    </td>
                    <td className="py-2 px-2">
                      <input
                        type="number"
                        value={ds.pre_cool_minutes}
                        onChange={(e) => updateDay(day, "pre_cool_minutes", parseInt(e.target.value) || 0)}
                        disabled={readOnly || !ds.is_operational}
                        className="rounded px-2 py-1 text-xs w-20"
                        style={{ ...inputStyle, opacity: ds.is_operational ? 1 : 0.4 }}
                        min={0}
                        max={180}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
