import { useCallback, useEffect, useState } from "react";
import { Radio, Shield } from "lucide-react";
import api from "../../lib/api";

interface SimbiotBridgeSettingsProps {
  siteId?: string;
  readOnly?: boolean;
  onError?: (error: string) => void;
  onSuccess?: () => void;
}

export function SimbiotBridgeSettings({
  siteId,
  readOnly = false,
  onError,
  onSuccess,
}: SimbiotBridgeSettingsProps) {
  const [bridgeEnabled, setBridgeEnabled] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const fetchBridgeState = useCallback(async () => {
    if (!siteId) { setLoading(false); return; }
    try {
      const data = await api.getSiteProcessing(siteId);
      setBridgeEnabled(data.sentinel_processing_enabled);
    } catch {
      setBridgeEnabled(null);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => { void fetchBridgeState(); }, [fetchBridgeState]);

  const handleToggle = useCallback(async () => {
    if (bridgeEnabled === null || toggling || readOnly) return;
    const next = !bridgeEnabled;
    setToggling(true);
    try {
      await api.toggleSiteProcessing(siteId!, next);
      setBridgeEnabled(next);
      onSuccess?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Failed to toggle bridge");
    } finally {
      setToggling(false);
    }
  }, [bridgeEnabled, toggling, readOnly, siteId, onError, onSuccess]);

  const isActive = bridgeEnabled === true;
  const isDisabled = loading || bridgeEnabled === null || toggling || readOnly;

  return (
    <div className="glass-panel overflow-hidden">
      <div
        className="p-4 border-b"
        style={{ borderColor: "var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{
              background: isActive ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
              color: isActive ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
            }}
          >
            <Radio className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              SIMBIOT Bridge
            </h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Controls the data valve between your BMS and SENTINEL. When disabled, no telemetry flows in.
            </p>
          </div>
        </div>
      </div>

      <div className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="flex items-center justify-center h-10 w-10 rounded-full"
              style={{
                background: isActive ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
              }}
            >
              <Shield
                className="h-5 w-5"
                style={{ color: isActive ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)" }}
              />
            </div>
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {loading ? "Loading..." : isActive ? "Bridge Active" : "Bridge Paused"}
              </p>
              <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {isActive
                  ? "Telemetry flowing from BMS → SIMBIOT → SENTINEL"
                  : "Data valve closed. Enable to resume telemetry ingestion."}
              </p>
            </div>
          </div>

          <button
            onClick={() => void handleToggle()}
            disabled={isDisabled}
            className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0"
            style={{
              background: isActive ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
              border: `1px solid ${isActive ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
              cursor: isDisabled ? "not-allowed" : "pointer",
              opacity: isDisabled ? 0.6 : 1,
            }}
            aria-label={isActive ? "Disable SIMBIOT Bridge" : "Enable SIMBIOT Bridge"}
          >
            <span
              className="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform"
              style={{
                background: "white",
                transform: isActive ? "translateX(24px)" : "translateX(2px)",
              }}
            />
          </button>
        </div>

        {readOnly && (
          <p className="mt-3 text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            Unlock settings to toggle the bridge.
          </p>
        )}
      </div>
    </div>
  );
}

export default SimbiotBridgeSettings;
