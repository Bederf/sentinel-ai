/**
 * Notification Channels Settings Component (Phase 102.4)
 *
 * Comprehensive UI for managing multi-channel technician notifications:
 * - Manage notification channels (Telegram, WhatsApp, SMS)
 * - Configure notification preferences (quiet hours, alert levels)
 * - View delivery logs
 * - Test channel verification
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  MessageCircle,
  Phone,
  Send,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Plus,
  Loader2,
} from "lucide-react";
import { authorizedFetch } from "@/lib/api";

interface NotificationChannel {
  id: string;
  channel_type: "telegram" | "whatsapp" | "sms";
  telegram_id?: string;
  whatsapp_number?: string;
  sms_number?: string;
  is_verified: boolean;
  verified_at?: string;
  verification_attempts: number;
  created_at: string;
  updated_at: string;
}

interface NotificationPreferences {
  id: string;
  preferred_channel: "telegram" | "whatsapp" | "sms";
  enabled_channels: ("telegram" | "whatsapp" | "sms")[];
  alert_level_min: "info" | "warning" | "critical";
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  emergency_override_enabled: boolean;
  batch_low_priority: boolean;
  batch_interval_minutes: number;
  created_at: string;
  updated_at: string;
}

interface DeliveryLog {
  id: string;
  technician_id: string;
  channel_type: string;
  recipient_identifier: string;
  status: "pending" | "sent" | "delivered" | "failed";
  error_message?: string;
  provider: string;
  sent_at?: string;
  created_at: string;
}

interface NotificationChannelsSettingsProps {
  technician_id: string;
  onError?: (msg: string) => void;
  onSuccess?: (msg: string) => void;
}

const CHANNEL_ICONS: Record<string, React.ReactNode> = {
  telegram: <MessageCircle className="h-5 w-5" />,
  whatsapp: <MessageCircle className="h-5 w-5" />,
  sms: <Phone className="h-5 w-5" />,
};

const CHANNEL_COLORS: Record<string, string> = {
  telegram: "rgba(59, 130, 246, 0.15)",
  whatsapp: "rgba(34, 197, 94, 0.15)",
  sms: "rgba(245, 158, 11, 0.15)",
};

const CHANNEL_TEXT_COLORS: Record<string, string> = {
  telegram: "var(--color-sentinel-blue)",
  whatsapp: "var(--color-sentinel-green)",
  sms: "var(--color-sentinel-amber)",
};

export function NotificationChannelsSettings({
  technician_id,
  onError,
  onSuccess,
}: NotificationChannelsSettingsProps) {
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [deliveryLogs, setDeliveryLogs] = useState<DeliveryLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"channels" | "preferences" | "logs">("channels");
  const [showAddChannel, setShowAddChannel] = useState(false);
  const [testingChannelId, setTestingChannelId] = useState<string | null>(null);
  const [savingPreferences, setSavingPreferences] = useState(false);

  // Stable ref for callbacks to avoid re-render loops
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // Load all data — only re-run when technician_id changes
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [channelsRes, prefsRes, logsRes] = await Promise.all([
        authorizedFetch(`/api/notifications/channels/${technician_id}`),
        authorizedFetch(`/api/notifications/preferences/${technician_id}`),
        authorizedFetch(`/api/notifications/delivery-logs?technician_id=${technician_id}&limit=20`),
      ]);

      if (channelsRes.ok) {
        setChannels(await channelsRes.json());
      }

      if (prefsRes.ok) {
        setPreferences(await prefsRes.json());
      } else {
        // If preferences don't exist, create defaults
        setPreferences({
          id: "",
          preferred_channel: "telegram",
          enabled_channels: ["telegram"],
          alert_level_min: "warning",
          quiet_hours_enabled: true,
          quiet_hours_start: "22:00",
          quiet_hours_end: "06:00",
          emergency_override_enabled: true,
          batch_low_priority: false,
          batch_interval_minutes: 60,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }

      if (logsRes.ok) {
        setDeliveryLogs(await logsRes.json());
      }
    } catch (error) {
      onErrorRef.current?.(`Failed to load notification settings: ${error}`);
    } finally {
      setLoading(false);
    }
  }, [technician_id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddChannel = async (type: "telegram" | "whatsapp" | "sms", identifier: string) => {
    try {
      const payload: Record<string, unknown> = {
        channel_type: type,
      };
      if (type === "telegram") payload.telegram_id = identifier;
      if (type === "whatsapp") payload.whatsapp_number = identifier;
      if (type === "sms") payload.sms_number = identifier;

      const res = await authorizedFetch(`/api/notifications/channels/${technician_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to create channel");
      }

      const newChannel = await res.json();
      setChannels([...channels, newChannel]);
      setShowAddChannel(false);
      onSuccess?.(`${type} channel added successfully`);
    } catch (error) {
      onError?.(`Failed to add channel: ${error}`);
    }
  };

  const handleDeleteChannel = async (channelId: string) => {
    if (!confirm("Are you sure you want to delete this channel?")) return;

    try {
      const res = await authorizedFetch(`/api/notifications/channels/${technician_id}/${channelId}`, {
        method: "DELETE",
      });

      if (!res.ok) throw new Error("Failed to delete channel");

      setChannels(channels.filter((c) => c.id !== channelId));
      onSuccess?.("Channel deleted successfully");
    } catch (error) {
      onError?.(`Failed to delete channel: ${error}`);
    }
  };

  const handleTestChannel = async (channelId: string) => {
    setTestingChannelId(channelId);
    try {
      const res = await authorizedFetch(`/api/notifications/channels/${technician_id}/${channelId}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          test_message_title: "SENTINEL Test",
          test_message_body: "This is a test notification from SENTINEL. If you received this, your notification channel is working correctly!",
        }),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.message || "Test failed");
      }

      const result = await res.json();
      if (result.success) {
        setChannels(
          channels.map((c) =>
            c.id === channelId
              ? { ...c, is_verified: true, verified_at: new Date().toISOString() }
              : c
          )
        );
        onSuccess?.("Test message sent and channel verified!");
      } else {
        onError?.(`Test failed: ${result.message}`);
      }
    } catch (error) {
      onError?.(`Test failed: ${error}`);
    } finally {
      setTestingChannelId(null);
    }
  };

  const handleSavePreferences = async () => {
    if (!preferences) return;
    setSavingPreferences(true);

    try {
      const res = await authorizedFetch(`/api/notifications/preferences/${technician_id}`, {
        method: preferences.id ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferred_channel: preferences.preferred_channel,
          enabled_channels: preferences.enabled_channels,
          alert_level_min: preferences.alert_level_min,
          quiet_hours_enabled: preferences.quiet_hours_enabled,
          quiet_hours_start: preferences.quiet_hours_start,
          quiet_hours_end: preferences.quiet_hours_end,
          emergency_override_enabled: preferences.emergency_override_enabled,
          batch_low_priority: preferences.batch_low_priority,
          batch_interval_minutes: preferences.batch_interval_minutes,
        }),
      });

      if (!res.ok) throw new Error("Failed to save preferences");

      const updated = await res.json();
      setPreferences(updated);
      onSuccess?.("Notification preferences saved successfully");
    } catch (error) {
      onError?.(`Failed to save preferences: ${error}`);
    } finally {
      setSavingPreferences(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div
          className="animate-spin h-6 w-6 border-2 rounded-full"
          style={{
            borderColor: "var(--color-sentinel-amber)",
            borderTopColor: "transparent",
          }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="flex gap-2 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        {[
          { id: "channels", label: "Channels", count: channels.length },
          { id: "preferences", label: "Preferences" },
          { id: "logs", label: "Delivery Logs", count: deliveryLogs.length },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
            style={{
              borderColor:
                activeTab === tab.id
                  ? "var(--color-sentinel-blue)"
                  : "transparent",
              color:
                activeTab === tab.id
                  ? "var(--color-sentinel-blue)"
                  : "var(--color-sentinel-text-secondary)",
            }}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Channels Tab */}
      {activeTab === "channels" && (
        <ChannelsTab
          channels={channels}
          onAddClick={() => setShowAddChannel(!showAddChannel)}
          onAdd={handleAddChannel}
          onDelete={handleDeleteChannel}
          onTest={handleTestChannel}
          testingId={testingChannelId}
          showAddForm={showAddChannel}
        />
      )}

      {/* Preferences Tab */}
      {activeTab === "preferences" && preferences && (
        <PreferencesTab
          preferences={preferences}
          channels={channels}
          onUpdate={setPreferences}
          onSave={handleSavePreferences}
          saving={savingPreferences}
        />
      )}

      {/* Logs Tab */}
      {activeTab === "logs" && (
        <LogsTab logs={deliveryLogs} />
      )}
    </div>
  );
}

// ========== Channels Tab Component ==========

function ChannelsTab({
  channels,
  onAddClick,
  onAdd,
  onDelete,
  onTest,
  testingId,
  showAddForm,
}: {
  channels: NotificationChannel[];
  onAddClick: () => void;
  onAdd: (type: "telegram" | "whatsapp" | "sms", identifier: string) => void;
  onDelete: (channelId: string) => void;
  onTest: (channelId: string) => void;
  testingId: string | null;
  showAddForm: boolean;
}) {
  const [channelType, setChannelType] = useState<"telegram" | "whatsapp" | "sms">("telegram");
  const [identifier, setIdentifier] = useState("");

  const handleSubmit = () => {
    if (!identifier.trim()) return;
    onAdd(channelType, identifier);
    setIdentifier("");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {channels.length} channel{channels.length !== 1 ? "s" : ""} configured
        </p>
        <button
          onClick={onAddClick}
          className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors"
          style={{
            background: "rgba(59, 130, 246, 0.15)",
            color: "var(--color-sentinel-blue)",
            border: "1px solid rgba(59, 130, 246, 0.3)",
          }}
        >
          <Plus className="h-4 w-4" />
          Add Channel
        </button>
      </div>

      {/* Add Channel Form */}
      {showAddForm && (
        <div
          className="p-4 rounded-lg"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Add New Channel
          </h3>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Channel Type
              </label>
              <select
                value={channelType}
                onChange={(e) => setChannelType(e.target.value as typeof channelType)}
                className="w-full px-3 py-2 rounded text-sm cursor-pointer"
                style={{
                  WebkitAppearance: "menulist",
                  appearance: "menulist",
                  background: "var(--color-sentinel-bg-panel)",
                  color: "var(--color-sentinel-text-primary)",
                  border: "1px solid var(--color-sentinel-border)",
                  position: "relative",
                  zIndex: 10,
                }}
              >
                <option value="telegram" style={{ background: "var(--color-sentinel-bg-panel)", color: "var(--color-sentinel-text-primary)" }}>Telegram</option>
                <option value="whatsapp" style={{ background: "var(--color-sentinel-bg-panel)", color: "var(--color-sentinel-text-primary)" }}>WhatsApp</option>
                <option value="sms" style={{ background: "var(--color-sentinel-bg-panel)", color: "var(--color-sentinel-text-primary)" }}>SMS</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {channelType === "telegram" && "Telegram User ID"}
                {channelType === "whatsapp" && "WhatsApp Phone (+27...)"}
                {channelType === "sms" && "SMS Phone (+27...)"}
              </label>
              <input
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder={
                  channelType === "telegram" ? "e.g. 123456789" : "e.g. +27123456789"
                }
                className="w-full px-3 py-2 rounded text-sm border-0"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSubmit}
                className="flex-1 px-3 py-2 rounded text-sm font-medium transition-colors"
                style={{
                  background: "var(--color-sentinel-blue)",
                  color: "white",
                  opacity: identifier.trim() ? 1 : 0.5,
                  cursor: identifier.trim() ? "pointer" : "default",
                }}
                disabled={!identifier.trim()}
              >
                Add Channel
              </button>
              <button
                onClick={onAddClick}
                className="px-3 py-2 rounded text-sm font-medium"
                style={{
                  background: "var(--color-sentinel-bg-panel)",
                  color: "var(--color-sentinel-text-secondary)",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Channels List */}
      <div className="space-y-2">
        {channels.length === 0 ? (
          <p className="text-sm text-center py-8" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            No notification channels configured. Click "Add Channel" to get started.
          </p>
        ) : (
          channels.map((channel) => (
            <div
              key={channel.id}
              className="p-4 rounded-lg flex items-center justify-between"
              style={{
                background: CHANNEL_COLORS[channel.channel_type],
                border: `1px solid ${CHANNEL_TEXT_COLORS[channel.channel_type]}30`,
              }}
            >
              <div className="flex items-center gap-3 flex-1">
                <div
                  className="p-2 rounded"
                  style={{
                    background: `${CHANNEL_TEXT_COLORS[channel.channel_type]}15`,
                    color: CHANNEL_TEXT_COLORS[channel.channel_type],
                  }}
                >
                  {CHANNEL_ICONS[channel.channel_type]}
                </div>
                <div>
                  <h3 className="text-sm font-semibold capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {channel.channel_type}
                  </h3>
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {channel.telegram_id || channel.whatsapp_number || channel.sms_number}
                  </p>
                  {channel.is_verified ? (
                    <div className="flex items-center gap-1 mt-1">
                      <CheckCircle2 className="h-3 w-3" style={{ color: "var(--color-sentinel-green)" }} />
                      <span className="text-xs" style={{ color: "var(--color-sentinel-green)" }}>
                        Verified
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1 mt-1">
                      <AlertCircle className="h-3 w-3" style={{ color: "var(--color-sentinel-amber)" }} />
                      <span className="text-xs" style={{ color: "var(--color-sentinel-amber)" }}>
                        Not verified
                      </span>
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onTest(channel.id)}
                  disabled={testingId === channel.id}
                  className="p-2 rounded transition-colors"
                  style={{
                    background: "rgba(59, 130, 246, 0.15)",
                    color: "var(--color-sentinel-blue)",
                    cursor: testingId === channel.id ? "not-allowed" : "pointer",
                    opacity: testingId === channel.id ? 0.6 : 1,
                  }}
                  title="Send test message"
                >
                  {testingId === channel.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={() => onDelete(channel.id)}
                  className="p-2 rounded transition-colors"
                  style={{
                    background: "rgba(220, 38, 38, 0.15)",
                    color: "var(--color-sentinel-red)",
                  }}
                  title="Delete channel"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ========== Preferences Tab Component ==========

function PreferencesTab({
  preferences,
  channels,
  onUpdate,
  onSave,
  saving,
}: {
  preferences: NotificationPreferences;
  channels: NotificationChannel[];
  onUpdate: (prefs: NotificationPreferences) => void;
  onSave: () => void;
  saving: boolean;
}) {
  const enabledChannels = channels.filter((c) =>
    preferences.enabled_channels.includes(c.channel_type)
  );

  return (
    <div className="space-y-6">
      {/* Preferred Channel */}
      <div
        className="p-4 rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Preferred Channel
        </h3>
        <p className="text-xs mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Primary channel for important notifications
        </p>
        <div className="flex gap-2">
          {enabledChannels.map((ch) => (
            <button
              key={ch.id}
              onClick={() => onUpdate({ ...preferences, preferred_channel: ch.channel_type })}
              className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors capitalize"
              style={{
                background:
                  preferences.preferred_channel === ch.channel_type
                    ? "rgba(59, 130, 246, 0.2)"
                    : "var(--color-sentinel-bg-panel)",
                color:
                  preferences.preferred_channel === ch.channel_type
                    ? "var(--color-sentinel-blue)"
                    : "var(--color-sentinel-text-secondary)",
                border:
                  preferences.preferred_channel === ch.channel_type
                    ? "1px solid rgba(59, 130, 246, 0.5)"
                    : "1px solid var(--color-sentinel-border)",
              }}
            >
              {ch.channel_type}
            </button>
          ))}
        </div>
      </div>

      {/* Enabled Channels */}
      <div
        className="p-4 rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Enabled Channels
        </h3>
        <p className="text-xs mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Send notifications to all of these channels
        </p>
        <div className="space-y-2">
          {channels.map((ch) => (
            <label key={ch.id} className="flex items-center gap-3 p-2 rounded cursor-pointer hover:bg-opacity-50"
              style={{
                background: preferences.enabled_channels.includes(ch.channel_type)
                  ? "rgba(16, 185, 129, 0.08)"
                  : "transparent",
              }}
            >
              <input
                type="checkbox"
                checked={preferences.enabled_channels.includes(ch.channel_type)}
                onChange={(e) => {
                  const channels = e.target.checked
                    ? [...preferences.enabled_channels, ch.channel_type]
                    : preferences.enabled_channels.filter((c) => c !== ch.channel_type);
                  onUpdate({ ...preferences, enabled_channels: channels });
                }}
                className="h-4 w-4 rounded"
              />
              <div>
                <span className="text-sm font-medium capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {ch.channel_type}
                </span>
                <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {ch.telegram_id || ch.whatsapp_number || ch.sms_number}
                </p>
              </div>
            </label>
          ))}
          {channels.length === 0 && (
            <p className="text-sm text-center py-4" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              Add channels first to enable them
            </p>
          )}
        </div>
      </div>

      {/* Alert Level Threshold */}
      <div
        className="p-4 rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Minimum Alert Level
        </h3>
        <p className="text-xs mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Only receive notifications at this severity level and above
        </p>
        <div className="flex gap-2">
          {["info", "warning", "critical"].map((level) => (
            <button
              key={level}
              onClick={() => onUpdate({ ...preferences, alert_level_min: level as typeof preferences.alert_level_min })}
              className="flex-1 px-3 py-2 rounded text-sm font-medium transition-colors capitalize"
              style={{
                background:
                  preferences.alert_level_min === level
                    ? level === "critical"
                      ? "rgba(220, 38, 38, 0.2)"
                      : level === "warning"
                        ? "rgba(245, 158, 11, 0.2)"
                        : "rgba(59, 130, 246, 0.2)"
                    : "var(--color-sentinel-bg-panel)",
                color:
                  preferences.alert_level_min === level
                    ? level === "critical"
                      ? "var(--color-sentinel-red)"
                      : level === "warning"
                        ? "var(--color-sentinel-amber)"
                        : "var(--color-sentinel-blue)"
                    : "var(--color-sentinel-text-secondary)",
                border:
                  preferences.alert_level_min === level
                    ? "1px solid " +
                      (level === "critical"
                        ? "rgba(220, 38, 38, 0.5)"
                        : level === "warning"
                          ? "rgba(245, 158, 11, 0.5)"
                          : "rgba(59, 130, 246, 0.5)")
                    : "1px solid var(--color-sentinel-border)",
              }}
            >
              {level}
            </button>
          ))}
        </div>
      </div>

      {/* Quiet Hours */}
      <div
        className="p-4 rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Quiet Hours
          </h3>
          <button
            onClick={() => onUpdate({ ...preferences, quiet_hours_enabled: !preferences.quiet_hours_enabled })}
            className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
            style={{
              background: preferences.quiet_hours_enabled ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-panel)",
            }}
          >
            <span
              className="inline-block h-4 w-4 rounded-full bg-white transition-transform"
              style={{ transform: preferences.quiet_hours_enabled ? "translateX(22px)" : "translateX(2px)" }}
            />
          </button>
        </div>
        <p className="text-xs mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Do not send notifications outside these times (unless critical with emergency override)
        </p>
        {preferences.quiet_hours_enabled && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  Start Time
                </label>
                <input
                  type="time"
                  value={preferences.quiet_hours_start}
                  onChange={(e) => onUpdate({ ...preferences, quiet_hours_start: e.target.value })}
                  className="w-full px-3 py-2 rounded text-sm border-0"
                  style={{
                    background: "var(--color-sentinel-bg-panel)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  End Time
                </label>
                <input
                  type="time"
                  value={preferences.quiet_hours_end}
                  onChange={(e) => onUpdate({ ...preferences, quiet_hours_end: e.target.value })}
                  className="w-full px-3 py-2 rounded text-sm border-0"
                  style={{
                    background: "var(--color-sentinel-bg-panel)",
                    color: "var(--color-sentinel-text-primary)",
                  }}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 p-2 rounded cursor-pointer">
              <input
                type="checkbox"
                checked={preferences.emergency_override_enabled}
                onChange={(e) => onUpdate({ ...preferences, emergency_override_enabled: e.target.checked })}
                className="h-4 w-4 rounded"
              />
              <span className="text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Allow CRITICAL alerts to bypass quiet hours
              </span>
            </label>
          </div>
        )}
      </div>

      {/* Save Button */}
      <button
        onClick={onSave}
        disabled={saving}
        className="w-full px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
        style={{
          background: "var(--color-sentinel-blue)",
          color: "white",
          opacity: saving ? 0.7 : 1,
          cursor: saving ? "not-allowed" : "pointer",
        }}
      >
        {saving && <Loader2 className="h-4 w-4 animate-spin" />}
        {saving ? "Saving..." : "Save Preferences"}
      </button>
    </div>
  );
}

// ========== Logs Tab Component ==========

function LogsTab({ logs }: { logs: DeliveryLog[] }) {
  return (
    <div className="space-y-2">
      {logs.length === 0 ? (
        <p className="text-sm text-center py-8" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          No delivery logs yet
        </p>
      ) : (
        logs.map((log) => (
          <div
            key={log.id}
            className="p-3 rounded-lg"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: `1px solid ${
                log.status === "sent"
                  ? "rgba(16, 185, 129, 0.3)"
                  : log.status === "failed"
                    ? "rgba(220, 38, 38, 0.3)"
                    : "var(--color-sentinel-border)"
              }`,
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {log.channel_type}
                  </span>
                  <span
                    className="text-xs px-2 py-0.5 rounded capitalize"
                    style={{
                      background:
                        log.status === "sent"
                          ? "rgba(16, 185, 129, 0.15)"
                          : log.status === "failed"
                            ? "rgba(220, 38, 38, 0.15)"
                            : "rgba(245, 158, 11, 0.15)",
                      color:
                        log.status === "sent"
                          ? "var(--color-sentinel-green)"
                          : log.status === "failed"
                            ? "var(--color-sentinel-red)"
                            : "var(--color-sentinel-amber)",
                    }}
                  >
                    {log.status}
                  </span>
                </div>
                <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {log.recipient_identifier}
                </p>
                {log.error_message && (
                  <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-red)" }}>
                    {log.error_message}
                  </p>
                )}
                <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  {new Date(log.created_at).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default NotificationChannelsSettings;
