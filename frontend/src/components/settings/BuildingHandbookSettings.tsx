import { useState, useEffect, useCallback } from "react";
import { BookOpen, Save, Upload, FileText } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

const SENTRY_BMS_SECRET = "sentry-bms-phase-41";
const SENTRY_BOT_API_KEY = "sentry-bot-RncXWQCYticUnuG06L4qnSUj-heKAeV0NnMdHOvIlKM3TNUv";

interface BuildingHandbookSettingsProps {
  siteId?: string;
  onError?: (error: string) => void;
  onSuccess?: (message: string) => void;
  readOnly?: boolean;
}

export function BuildingHandbookSettings({
  siteId = "site-002",
  onError,
  onSuccess,
  readOnly = false,
}: BuildingHandbookSettingsProps) {
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [source, setSource] = useState<"database" | "filesystem" | "not_found">("database");

  const fetchHandbook = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authorizedFetch(
        `/api/sentry/building-handbook?site_id=${encodeURIComponent(siteId)}`,
        { headers: { "X-Sentry-API-Key": SENTRY_BOT_API_KEY, "X-Sentry-Secret": SENTRY_BMS_SECRET } }
      );
      if (!response.ok) throw new Error("Failed to fetch handbook");
      const data = await response.json();
      setContent(data.content || "");
      setSource(data.source || "not_found");
      setDirty(false);
    } catch {
      onError?.("Failed to load building handbook");
    } finally {
      setLoading(false);
    }
  }, [onError, siteId]);

  useEffect(() => { fetchHandbook(); }, [fetchHandbook]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await authorizedFetch("/api/sentry/building-handbook", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Sentry-API-Key": SENTRY_BOT_API_KEY,
          "X-Sentry-Secret": SENTRY_BMS_SECRET,
        },
        body: JSON.stringify({
          site_id: siteId,
          content,
          uploaded_by: localStorage.getItem("sentinel_user") || "settings-ui",
        }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to save handbook");
      }
      setDirty(false);
      onSuccess?.("Building handbook saved successfully");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to save handbook");
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".md")) {
      onError?.("Only .md markdown files are supported");
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setContent(text);
      setDirty(true);
    };
    reader.readAsText(file);
  };

  const inputStyle = {
    background: "var(--color-sentinel-bg-secondary)",
    border: "1px solid var(--glass-border)",
    color: "var(--color-sentinel-text-primary)",
  };

  const sourceLabel = {
    database: { label: "Database", color: "var(--color-sentinel-green)" },
    filesystem: { label: "Filesystem fallback", color: "var(--color-sentinel-amber)" },
    not_found: { label: "Not found", color: "var(--color-sentinel-red)" },
  };

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <BookOpen className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Building Handbook
              </h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Site-specific BUILDING_HANDBOOK.md for staff bot responses
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ background: `${sourceLabel[source].color}20`, color: sourceLabel[source].color }}
            >
              {sourceLabel[source].label}
            </span>
            {!readOnly && !loading && content && (
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving || !dirty}
                className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium transition-colors hover:brightness-110 disabled:opacity-50"
                style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)", border: "1px solid rgba(16, 185, 129, 0.3)" }}
              >
                <Save className="h-3 w-3" />
                {saving ? "Saving..." : "Save"}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="p-4 space-y-3">
        {!readOnly && (
          <div className="flex items-center gap-3">
            <label
              htmlFor="handbook-file-upload"
              className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium cursor-pointer transition-colors hover:brightness-110"
              style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.3)" }}
            >
              <Upload className="h-3 w-3" />
              Upload .md
              <input
                id="handbook-file-upload"
                type="file"
                accept=".md,text/markdown"
                className="hidden"
                onChange={handleFileUpload}
              />
            </label>
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              or edit the content below
            </span>
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 p-4">
            <div className="animate-spin h-4 w-4 border-2 rounded-full" style={{ borderColor: "var(--color-sentinel-border)", borderTopColor: "var(--color-sentinel-blue)" }} />
            <span className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading handbook...</span>
          </div>
        ) : (
          <textarea
            value={content}
            onChange={(e) => { setContent(e.target.value); setDirty(true); }}
            readOnly={readOnly}
            rows={24}
            className="w-full rounded px-3 py-2 text-sm font-mono leading-relaxed resize-y"
            style={{
              ...inputStyle,
              minHeight: "400px",
            }}
            placeholder="No handbook content found. Upload a BUILDING_HANDBOOK.md file or paste content here."
          />
        )}

        {!readOnly && content && (
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            <FileText className="h-3 w-3" />
            <span>
              {content.split(/\s+/).filter(Boolean).length} words · {content.length} chars
              {dirty && " · unsaved changes"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
