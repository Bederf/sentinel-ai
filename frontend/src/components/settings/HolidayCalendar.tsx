import { useState, useEffect, useCallback } from "react";
import { Calendar, Plus, Trash2 } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface Holiday {
  id: string;
  date: string;
  name: string;
  type: string;
  recurring: boolean;
  editable: boolean;
}

interface HolidayCalendarProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: () => void;
  readOnly?: boolean;
}

export function HolidayCalendar({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: HolidayCalendarProps) {
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newRecurring, setNewRecurring] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const fetchHolidays = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authorizedFetch(`/api/buildings/${siteId}/holidays`);
      if (!response.ok) throw new Error("Failed to fetch holidays");
      const data = await response.json();
      setHolidays(data.holidays || []);
    } catch {
      onError?.("Failed to load holidays");
    } finally {
      setLoading(false);
    }
  }, [siteId, onError]);

  useEffect(() => { fetchHolidays(); }, [fetchHolidays]);

  const handleAdd = async () => {
    if (!newName.trim() || !newDate) return;
    setAdding(true);
    try {
      const response = await authorizedFetch(`/api/buildings/${siteId}/holidays`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date: newRecurring ? newDate.slice(5) : newDate, // MM-DD for recurring, YYYY-MM-DD for one-time
          name: newName.trim(),
          recurring: newRecurring,
        }),
      });
      if (!response.ok) throw new Error("Failed to add holiday");
      setNewName("");
      setNewDate("");
      setNewRecurring(false);
      setShowAddForm(false);
      await fetchHolidays();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to add holiday");
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (holidayId: string) => {
    try {
      const response = await authorizedFetch(`/api/buildings/${siteId}/holidays/${holidayId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to remove holiday");
      await fetchHolidays();
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to remove holiday");
    }
  };

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  const publicHolidays = holidays.filter((h) => h.type === "public");
  const customHolidays = holidays.filter((h) => h.type === "custom");

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(168, 85, 247, 0.15)", color: "rgb(168, 85, 247)" }}>
              <Calendar className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Holiday Calendar</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                SA public holidays + custom building holidays
              </p>
            </div>
          </div>
          {!readOnly && (
            <button
              type="button"
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
              style={{
                background: "rgba(16, 185, 129, 0.15)",
                color: "var(--color-sentinel-green)",
                border: "1px solid rgba(16, 185, 129, 0.3)",
              }}
            >
              <Plus className="h-3 w-3" />
              Add Holiday
            </button>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Add Form */}
        {showAddForm && !readOnly && (
          <div className="p-3 rounded-lg space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Holiday Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Company Day"
                  className="w-full rounded px-3 py-1.5 text-xs"
                  style={inputStyle}
                />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>Date</label>
                <input
                  type="date"
                  value={newDate}
                  onChange={(e) => setNewDate(e.target.value)}
                  className="w-full rounded px-3 py-1.5 text-xs"
                  style={inputStyle}
                />
              </div>
              <div className="flex items-end gap-3">
                <label className="flex items-center gap-2 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={newRecurring}
                    onChange={(e) => setNewRecurring(e.target.checked)}
                  />
                  Recurring annually
                </label>
                <button
                  type="button"
                  onClick={() => void handleAdd()}
                  disabled={adding || !newName.trim() || !newDate}
                  className="px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110"
                  style={{
                    background: "rgba(59, 130, 246, 0.15)",
                    color: "var(--color-sentinel-blue)",
                    border: "1px solid rgba(59, 130, 246, 0.3)",
                    opacity: adding || !newName.trim() || !newDate ? 0.5 : 1,
                  }}
                >
                  {adding ? "Adding..." : "Add"}
                </button>
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading holidays...</p>
        ) : (
          <>
            {/* SA Public Holidays */}
            <div>
              <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                SA Public Holidays ({publicHolidays.length})
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5">
                {publicHolidays.map((h) => {
                  // For recurring MM-DD holidays, show current year so they always look fresh
                  const displayDate = h.recurring && h.date.includes("-") && !h.date.startsWith("20")
                    ? `${new Date().getFullYear()}-${h.date}`
                    : h.date;
                  return (
                    <div key={h.id} className="flex items-center gap-2 px-2 py-1.5 rounded text-xs" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                      <span className="font-mono" style={{ color: "var(--color-sentinel-blue)" }}>{displayDate}</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{h.name}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Custom Holidays */}
            {customHolidays.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Custom Holidays ({customHolidays.length})
                </h3>
                <div className="space-y-1.5">
                  {customHolidays.map((h) => (
                    <div key={h.id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded text-xs" style={{ background: "var(--color-sentinel-bg-secondary)" }}>
                      <div className="flex items-center gap-2">
                        <span className="font-mono" style={{ color: "var(--color-sentinel-green)" }}>{h.date}</span>
                        <span style={{ color: "var(--color-sentinel-text-primary)" }}>{h.name}</span>
                        {h.recurring && (
                          <span className="px-1 py-0.5 rounded text-[10px]" style={{ background: "rgba(168, 85, 247, 0.15)", color: "rgb(168, 85, 247)" }}>
                            recurring
                          </span>
                        )}
                      </div>
                      {!readOnly && h.editable && (
                        <button
                          type="button"
                          onClick={() => void handleDelete(h.id)}
                          className="p-1 rounded hover:brightness-110"
                          style={{ color: "var(--color-sentinel-red)" }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
