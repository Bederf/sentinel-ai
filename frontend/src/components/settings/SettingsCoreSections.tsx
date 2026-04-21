import type { ReactNode } from "react";
import { Gauge, Lock, Monitor, Settings as SettingsIcon, Shield, Unlock } from "lucide-react";
import { PasswordModal } from "../PasswordModal";
import { RiskThresholdEditor } from "../RiskThresholdEditor";
import { SafetyRulesEditor } from "../SafetyRulesEditor";
import { SiteSelector } from "../SiteSelector";
import { ThresholdEditor } from "../ThresholdEditor";
import type { useSettingsController } from "./useSettingsController";

function SettingsTitleBlock({ selectedSiteId }: { selectedSiteId: string | null }) {
  return (
    <div className="flex items-center gap-3">
      <SettingsIcon className="h-8 w-8" style={{ color: "var(--color-sentinel-amber)" }} />
      <div>
        <h1 className="text-2xl font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          System Settings
        </h1>
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {selectedSiteId || "No site selected"}
        </p>
      </div>
    </div>
  );
}

function SettingsUnlockButton({
  setSettingsPageUnlocked,
  setShowPasswordModal,
  settingsPageUnlocked,
}: Pick<ReturnType<typeof useSettingsController>, "setSettingsPageUnlocked" | "setShowPasswordModal" | "settingsPageUnlocked">) {
  return (
    <button
      onClick={() => {
        if (settingsPageUnlocked) {
          setSettingsPageUnlocked(false);
        } else {
          setShowPasswordModal(true);
        }
      }}
      className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors hover:brightness-110"
      style={{
        background: settingsPageUnlocked ? "rgba(245, 158, 11, 0.15)" : "rgba(220, 38, 38, 0.15)",
        color: settingsPageUnlocked ? "var(--color-sentinel-amber)" : "var(--color-sentinel-red)",
        border: `1px solid ${settingsPageUnlocked ? "rgba(245, 158, 11, 0.3)" : "rgba(220, 38, 38, 0.3)"}`,
      }}
      type="button"
    >
      {settingsPageUnlocked ? (
        <>
          <Lock className="h-4 w-4" />
          Lock Settings
        </>
      ) : (
        <>
          <Unlock className="h-4 w-4" />
          Unlock to Edit
        </>
      )}
    </button>
  );
}

export function SettingsLoadingState() {
  return (
    <div className="h-full flex items-center justify-center" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="text-center">
        <div
          className="animate-spin h-8 w-8 border-4 rounded-full mx-auto mb-4"
          style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }}
        />
        <p style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading settings...</p>
      </div>
    </div>
  );
}

export function SettingsHeader({
  controller,
}: {
  controller: ReturnType<typeof useSettingsController>;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center justify-between gap-3 mb-2">
        <SettingsTitleBlock selectedSiteId={controller.selectedSiteId} />
        <SettingsUnlockButton
          setSettingsPageUnlocked={controller.setSettingsPageUnlocked}
          setShowPasswordModal={controller.setShowPasswordModal}
          settingsPageUnlocked={controller.settingsPageUnlocked}
        />
      </div>
      <p style={{ color: "var(--color-sentinel-text-secondary)" }}>
        Configure global system settings and preferences
      </p>
      <div className="mt-4 max-w-sm">
        <SiteSelector
          sites={controller.buildings}
          selectedSiteId={controller.selectedSiteId}
          onSiteChange={controller.handleSiteChange}
          includeAllOption={false}
        />
      </div>
    </div>
  );
}

function SettingsBanner({
  children,
  color,
}: {
  children: ReactNode;
  color: "amber" | "green";
}) {
  const tone = color === "amber"
    ? { background: "rgba(245, 158, 11, 0.15)", border: "1px solid rgba(245, 158, 11, 0.3)", text: "var(--color-sentinel-amber)" }
    : { background: "rgba(16, 185, 129, 0.15)", border: "1px solid rgba(16, 185, 129, 0.3)", text: "var(--color-sentinel-green)" };

  return (
    <div className="mb-6 flex items-center gap-2 p-3 rounded-md" style={{ background: tone.background, border: tone.border }}>
      <div style={{ color: tone.text }}>{children}</div>
    </div>
  );
}

export function SettingsStatusBanners({
  controller,
}: {
  controller: ReturnType<typeof useSettingsController>;
}) {
  return (
    <>
      {controller.currentUserRole !== "admin" && controller.settingsPageUnlocked ? (
        <SettingsBanner color="amber">
          <div className="flex items-center gap-2">
            <Unlock className="h-4 w-4" style={{ color: "var(--color-sentinel-amber)" }} />
            <span className="text-sm" style={{ color: "var(--color-sentinel-amber)" }}>
              Settings page is unlocked. Click "Lock Settings" when finished making changes.
            </span>
          </div>
        </SettingsBanner>
      ) : null}

      {controller.saveSuccess ? (
        <SettingsBanner color="green">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full" style={{ background: "var(--color-sentinel-green)" }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-green)" }}>
              Settings saved successfully
            </p>
          </div>
        </SettingsBanner>
      ) : null}
    </>
  );
}

function SettingsPanelFrame({
  children,
  description,
  icon,
  iconBackground,
  iconColor,
  title,
}: {
  children: ReactNode;
  description: string;
  icon: ReactNode;
  iconBackground: string;
  iconColor: string;
  title: string;
}) {
  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: iconBackground, color: iconColor }}>
            {icon}
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {title}
            </h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {description}
            </p>
          </div>
        </div>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function HealthThresholdPanel({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  return (
    <SettingsPanelFrame
      description="Configure the health score boundaries for equipment classification"
      icon={<Monitor className="h-5 w-5" />}
      iconBackground="rgba(16, 185, 129, 0.15)"
      iconColor="var(--color-sentinel-green)"
      title="Health Score Thresholds"
    >
      {controller.healthThresholdError ? (
        <div className="p-4 rounded-md text-center" style={{ background: "rgba(220, 38, 38, 0.15)", border: "1px solid rgba(220, 38, 38, 0.3)" }}>
          <p style={{ color: "var(--color-sentinel-red)" }}>Failed to load thresholds</p>
        </div>
      ) : (
        <ThresholdEditor
          healthy={controller.healthThresholds.healthy}
          warning={controller.healthThresholds.warning}
          critical={controller.healthThresholds.critical}
          onSave={controller.handleSaveThresholds}
        />
      )}
    </SettingsPanelFrame>
  );
}

function RiskThresholdPanel({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  return (
    <SettingsPanelFrame
      description="Configure how cockpit and heat map severity bands interpret risk scores"
      icon={<Gauge className="h-5 w-5" />}
      iconBackground="rgba(249, 115, 22, 0.15)"
      iconColor="var(--color-sentinel-amber)"
      title="Cockpit Risk Thresholds"
    >
      {controller.riskThresholdError ? (
        <div className="rounded-md p-4 text-center" style={{ background: "rgba(220, 38, 38, 0.15)", border: "1px solid rgba(220, 38, 38, 0.3)" }}>
          <p style={{ color: "var(--color-sentinel-red)" }}>Failed to load risk thresholds</p>
        </div>
      ) : (
        <RiskThresholdEditor
          medium={controller.riskThresholds.medium}
          high={controller.riskThresholds.high}
          critical={controller.riskThresholds.critical}
          onSave={controller.handleSaveRiskThresholds}
        />
      )}
    </SettingsPanelFrame>
  );
}

function SafetyRulesPanel({
  controller,
  onError,
}: {
  controller: ReturnType<typeof useSettingsController>;
  onError?: (error: string) => void;
}) {
  return (
    <SettingsPanelFrame
      description="Configure safety interlocks and validation rules for device control"
      icon={<Shield className="h-5 w-5" />}
      iconBackground="rgba(220, 38, 38, 0.15)"
      iconColor="var(--color-sentinel-red)"
      title="Safety Rules"
    >
      <SafetyRulesEditor onError={onError} onSuccess={controller.handleSuccess} readOnly={controller.readOnly} />
    </SettingsPanelFrame>
  );
}

export function ThresholdSettingsSection({
  controller,
  onError,
}: {
  controller: ReturnType<typeof useSettingsController>;
  onError?: (error: string) => void;
}) {
  return (
    <>
      <HealthThresholdPanel controller={controller} />
      <RiskThresholdPanel controller={controller} />
      <SafetyRulesPanel controller={controller} onError={onError} />
    </>
  );
}

export function SettingsPasswordModal({
  controller,
}: {
  controller: ReturnType<typeof useSettingsController>;
}) {
  return (
    <PasswordModal
      isOpen={controller.showPasswordModal}
      onClose={() => controller.setShowPasswordModal(false)}
      onSuccess={() => controller.setSettingsPageUnlocked(true)}
      title="Unlock Settings Page"
      description="This page requires a password to modify settings. Enter the admin password to make changes to safety rules, feature access, and other configurations."
    />
  );
}
