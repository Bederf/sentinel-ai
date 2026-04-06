import { memo, useState } from "react";
import { Bell } from "lucide-react";
import { NotificationChannelsSettings } from "../NotificationChannelsSettings";
import { NotificationSettings } from "../NotificationSettings";

interface NotificationSettingsPanelProps {
  currentUserEmail: string;
  hasAuthenticatedSession: boolean;
  siteId?: string;
  onError?: (msg: string) => void;
  onSuccess?: () => void;
}

function NotificationPanelHeader({ detail }: { detail: string }) {
  return (
    <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
      <div className="flex items-center gap-3">
        <div
          className="p-2 rounded"
          style={{
            background: "rgba(245, 158, 11, 0.15)",
            color: "var(--color-sentinel-amber)",
          }}
        >
          <Bell className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Notification Settings
          </h2>
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {detail}
          </p>
        </div>
      </div>
    </div>
  );
}

function NotificationTabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
      style={{
        borderColor: active ? "var(--color-sentinel-blue)" : "transparent",
        color: active ? "var(--color-sentinel-blue)" : "var(--color-sentinel-text-secondary)",
      }}
      type="button"
    >
      {label}
    </button>
  );
}

function NotificationUnauthenticatedState() {
  return (
    <div className="glass-panel overflow-hidden">
      <NotificationPanelHeader detail="Sign in again to manage multi-channel notifications and SENTRY bot preferences." />
    </div>
  );
}

function NotificationTabbedContent({
  currentUserEmail,
  onError,
  onSuccess,
}: {
  currentUserEmail: string;
  onError?: (msg: string) => void;
  onSuccess?: () => void;
}) {
  const [notifTab, setNotifTab] = useState<"sentry" | "channels">("channels");

  return (
    <div className="glass-panel overflow-hidden">
      <NotificationPanelHeader detail="Configure multi-channel notifications and SENTRY bot preferences" />
      <div className="p-4">
        <div className="flex gap-2 border-b mb-6" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <NotificationTabButton
            active={notifTab === "channels"}
            label="Multi-Channel (Phase 102)"
            onClick={() => setNotifTab("channels")}
          />
          <NotificationTabButton
            active={notifTab === "sentry"}
            label="SENTRY Bot Alert Commands"
            onClick={() => setNotifTab("sentry")}
          />
        </div>

        {notifTab === "channels" ? (
          <NotificationChannelsSettings
            technician_id={currentUserEmail}
            onError={onError}
            onSuccess={onSuccess}
          />
        ) : (
          <NotificationSettings onError={onError} onSuccess={onSuccess} />
        )}
      </div>
    </div>
  );
}

export const NotificationSettingsPanel = memo(function NotificationSettingsPanel({
  currentUserEmail,
  hasAuthenticatedSession,
  siteId: _siteId,
  onError,
  onSuccess,
}: NotificationSettingsPanelProps) {
  if (!hasAuthenticatedSession || !currentUserEmail) {
    return <NotificationUnauthenticatedState />;
  }

  return (
    <NotificationTabbedContent
      currentUserEmail={currentUserEmail}
      onError={onError}
      onSuccess={onSuccess}
    />
  );
});
