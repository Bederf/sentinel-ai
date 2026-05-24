import { Monitor } from "lucide-react";
import type { View } from "../../lib/navigation";
import { ThemeSwitcher } from "../ThemeSwitcher";
import { AegisSettings } from "./AegisSettings";
import { AiCostTracker } from "./AiCostTracker";
import { AiRuntimePolicySettings } from "./AiRuntimePolicySettings";
import { AlertMuting } from "./AlertMuting";
import { AlertRoutingRules } from "./AlertRoutingRules";
import { BuildingConfigEditor } from "./BuildingConfigEditor";
import { BuildingHandbookSettings } from "./BuildingHandbookSettings";
import { ChannelStatusDashboard } from "./ChannelStatusDashboard";
import { GlassThemeControls } from "./GlassThemeControls";
import { HolidayCalendar } from "./HolidayCalendar";
import { OnboardingPhaseSettings } from "./OnboardingPhaseSettings";
import { ModuleAccessSections } from "./SettingsModuleSections";
import {
  SettingsHeader,
  SettingsLoadingState,
  SettingsPasswordModal,
  SettingsStatusBanners,
  ThresholdSettingsSection,
} from "./SettingsCoreSections";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";
import { OperatingScheduleEditor } from "./OperatingScheduleEditor";
import { SimbiotBridgeSettings } from "./SimbiotBridgeSettings";
import { SpaceOptimizationSettings } from "./SpaceOptimizationSettings";
import { SystemHealthDashboard } from "./SystemHealthDashboard";
import { TariffManager } from "./TariffManager";
import { TechnicianRegistry } from "./TechnicianRegistry";
import { ManagerRegistry } from "./ManagerRegistry";
import type { useSettingsController } from "./useSettingsController";

interface SettingsPageViewProps {
  controller: ReturnType<typeof useSettingsController>;
  onError?: (error: string) => void;
  onNavigate?: (view: View) => void;
}

function DisplaySettingsSection({
  controller: _controller,
  onError: _onError,
}: {
  controller: ReturnType<typeof useSettingsController>;
  onError?: (error: string) => void;
}) {
  return (
    <>
      <div className="glass-panel overflow-visible">
        <div className="p-4 border-b rounded-t-lg" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <Monitor className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Display Settings</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Customize Apple Glass theme appearance</p>
            </div>
          </div>
        </div>
        <div className="p-6 space-y-6">
          <div className="space-y-3">
            <label className="block text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Select Theme
            </label>
            <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Switch between Sentinel Dark, Matrix, Glass, and Dark Ops themes
            </p>
            <ThemeSwitcher />
          </div>
          <div style={{ height: "1px", background: "var(--color-sentinel-border)" }} />
          <GlassThemeControls />
        </div>
      </div>
    </>
  );
}

function SettingsSections({
  controller,
  onError,
  onNavigate,
}: SettingsPageViewProps) {
  return (
    <div className="space-y-6 max-w-4xl">
      <OnboardingPhaseSettings
        selectedSiteId={controller.selectedSiteId ?? undefined}
        sites={controller.buildings}
        currentUserRole={controller.currentUserRole}
        readOnly={controller.readOnly}
        onError={onError}
        onSuccess={controller.handleSuccess}
      />
      <SystemHealthDashboard onError={onError} onNavigate={onNavigate} />
      <AiCostTracker onError={onError} siteId={controller.selectedSiteId ?? undefined} />
      <AiRuntimePolicySettings
        siteId={controller.selectedSiteId ?? undefined}
        currentUserRole={controller.currentUserRole}
        readOnly={controller.readOnly}
        onError={onError}
        onSuccess={controller.handleSuccess}
      />
      <ThresholdSettingsSection controller={controller} onError={onError} />
      <NotificationSettingsPanel
        currentUserEmail={controller.currentUserEmail}
        hasAuthenticatedSession={controller.hasSessionToken}
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
      />
      <ChannelStatusDashboard onError={onError} siteId={controller.selectedSiteId ?? undefined} />
      <AlertRoutingRules
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <AlertMuting
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <TechnicianRegistry
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <ManagerRegistry
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <SimbiotBridgeSettings
        siteId={controller.selectedSiteId ?? undefined}
        readOnly={controller.readOnly}
        onError={onError}
        onSuccess={controller.handleSuccess}
      />
      <AegisSettings
        siteId={controller.selectedSiteId ?? undefined}
        currentUserRole={controller.currentUserRole}
        readOnly={controller.readOnly}
        onError={onError}
        onSuccess={controller.handleSuccess}
      />
      {controller.isModuleActive("space_optimization") ? (
        <SpaceOptimizationSettings
          siteId={controller.selectedSiteId ?? undefined}
          onError={onError}
          onSuccess={controller.handleSuccess}
          readOnly={controller.readOnly}
        />
      ) : null}
      <BuildingConfigEditor
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <BuildingHandbookSettings
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <OperatingScheduleEditor
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <HolidayCalendar
        siteId={controller.selectedSiteId ?? undefined}
        onError={onError}
        onSuccess={controller.handleSuccess}
        readOnly={controller.readOnly}
      />
      <TariffManager siteId={controller.selectedSiteId ?? undefined} onError={onError} readOnly={controller.readOnly} />
      <ModuleAccessSections controller={controller} onError={onError} />
      <DisplaySettingsSection controller={controller} onError={onError} />
    </div>
  );
}

export function SettingsPageView({ controller, onError, onNavigate }: SettingsPageViewProps) {
  if (controller.loading) {
    return <SettingsLoadingState />;
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <SettingsHeader controller={controller} />
      <SettingsStatusBanners controller={controller} />
      <SettingsSections controller={controller} onError={onError} onNavigate={onNavigate} />
      <SettingsPasswordModal controller={controller} />
    </div>
  );
}
