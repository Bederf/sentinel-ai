import { useState, useEffect, useCallback } from "react";
import { Radio, CheckCircle, XCircle, AlertTriangle, Send } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface ChannelStatus {
  channel: string;
  provider?: string;
  status: "active" | "inactive" | "error";
  last_checked?: string;
  error?: string;
  message_count?: number;
}

interface ChannelStatusDashboardProps {
  siteId?: string;
  onError?: (error: string) => void;
}

export function ChannelStatusDashboard({ siteId: _siteId, onError }: ChannelStatusDashboardProps) {
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      // Source of truth: backend notification providers status endpoint.
      const response = await authorizedFetch("/api/notifications/providers/status", { method: "GET" });
      if (response.ok) {
        const providers = (await response.json()) as Array<{
          channel: string;
          provider: string;
          enabled: boolean;
        }>;
        const byChannel = new Map(providers.map((p) => [p.channel.toLowerCase(), p]));
        const statuses: ChannelStatus[] = [
          {
            channel: "Telegram",
            provider: byChannel.get("telegram")?.provider,
            status: byChannel.get("telegram")?.enabled ? "active" : "inactive",
            message_count: 0,
          },
          {
            channel: "WhatsApp",
            provider: byChannel.get("whatsapp")?.provider,
            status: byChannel.get("whatsapp")?.enabled ? "active" : "inactive",
            message_count: 0,
          },
          {
            channel: "Email",
            provider: byChannel.get("email")?.provider,
            status: byChannel.get("email")?.enabled ? "active" : "inactive",
            message_count: 0,
          },
          {
            channel: "SMS",
            provider: byChannel.get("sms")?.provider,
            status: byChannel.get("sms")?.enabled ? "active" : "inactive",
            message_count: 0,
          },
        ];
        setChannels(statuses);
      } else {
        // If backend status probe fails, show all channels as inactive.
        setChannels([
          { channel: "Telegram", status: "inactive" },
          { channel: "WhatsApp", status: "inactive" },
          { channel: "Email", status: "inactive" },
          { channel: "SMS", status: "inactive" },
        ]);
      }
    } catch {
      setChannels([
        { channel: "Telegram", status: "inactive" },
        { channel: "WhatsApp", status: "inactive" },
        { channel: "Email", status: "inactive" },
        { channel: "SMS", status: "inactive" },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleTest = async (channel: string) => {
    const channelKey = channel.toLowerCase();
    setTesting(channel);
    try {
      // Send provider test via notifications API.
      const response = await authorizedFetch("/api/notifications/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: channelKey }),
      });
      if (!response.ok) throw new Error(`Test failed for ${channel}`);
      onError?.(`Test message sent to ${channel}`); // Using onError as notification
    } catch {
      onError?.(`Failed to send test to ${channel}`);
    } finally {
      setTesting(null);
    }
  };

  const statusIcon = (status: string) => {
    if (status === "active") return <CheckCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />;
    if (status === "error") return <XCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />;
    return <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />;
  };

  const statusText = (status: string) => {
    if (status === "active") return { color: "var(--color-sentinel-green)", label: "Active" };
    if (status === "error") return { color: "var(--color-sentinel-red)", label: "Error" };
    return { color: "var(--color-sentinel-text-secondary)", label: "Not configured" };
  };

  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
            <Radio className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Notification Channels</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Channel status and connectivity
            </p>
          </div>
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading channel status...</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {channels.map((ch) => {
              const st = statusText(ch.status);
              return (
                <div key={ch.channel} className="p-3 rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{ch.channel}</span>
                    {statusIcon(ch.status)}
                  </div>
                  <p className="text-xs" style={{ color: st.color }}>{st.label}</p>
                  {ch.provider && (
                    <p className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {ch.provider}
                    </p>
                  )}
                  {ch.message_count !== undefined && ch.message_count > 0 && (
                    <p className="text-[10px] mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {ch.message_count} messages sent
                    </p>
                  )}
                  {ch.status === "active" && (
                    <button
                      type="button"
                      onClick={() => void handleTest(ch.channel)}
                      disabled={testing === ch.channel}
                      className="mt-2 flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors hover:brightness-110"
                      style={{ background: "rgba(59, 130, 246, 0.1)", color: "var(--color-sentinel-blue)", border: "1px solid rgba(59, 130, 246, 0.2)" }}
                    >
                      <Send className="h-2.5 w-2.5" />
                      {testing === ch.channel ? "Sending..." : "Send Test"}
                    </button>
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
