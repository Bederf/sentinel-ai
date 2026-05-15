import type { ReactNode } from "react";
import { Brain, Gauge, Zap } from "lucide-react";
import { ModuleDescriptions } from "./ModuleDescriptions";
import {
  getAddonToggleCards,
  getBuildingSystemCards,
  getPlatformStatusCards,
  type BuildingSystemCard,
  type FeatureToggleCard,
} from "./settingsCatalog";
import type { useSettingsController } from "./useSettingsController";

function MLTrainingCard({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  const disabled = controller.mlTrainingLoading || !controller.canToggleModules;

  return (
    <div className="mt-4 rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="p-1.5 rounded" style={{ background: "rgba(168, 85, 247, 0.15)", color: "rgb(168, 85, 247)" }}>
            <Brain className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>ML Background Training</h3>
            <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Periodic model retraining, drift detection, and feedback loops. CPU-intensive — disable on resource-constrained servers.
            </p>
            <p className="mt-1 text-[10px]" style={{ color: "var(--color-sentinel-text-tertiary, var(--color-sentinel-text-secondary))" }}>
              Takes effect on next service restart.
            </p>
          </div>
        </div>
        <button
          onClick={() => void controller.handleMlTrainingToggle()}
          disabled={disabled}
          className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0"
          style={{
            background: controller.mlTrainingEnabled ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
            border: `1px solid ${controller.mlTrainingEnabled ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.6 : 1,
          }}
          aria-label="Toggle ML background training"
          type="button"
        >
          <span className="inline-block h-4 w-4 rounded-full bg-white transition-transform" style={{ transform: controller.mlTrainingEnabled ? "translateX(22px)" : "translateX(2px)" }} />
        </button>
      </div>
    </div>
  );
}

function ModuleCard({
  children,
  description,
  icon,
  title,
}: {
  children: ReactNode;
  description: string;
  icon: ReactNode;
  title: string;
}) {
  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
            {icon}
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{title}</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>{description}</p>
          </div>
        </div>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function PlatformModuleCard({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  const platformCards = getPlatformStatusCards(controller.availableModules);

  return (
    <ModuleCard description="Core platform modules (always active)" icon={<Zap className="h-5 w-5" />} title="Platform">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {platformCards.map((card) => (
          <div key={card.id} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{card.label}</h3>
                <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
              </div>
              <div className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
                Active
              </div>
            </div>
          </div>
        ))}
      </div>
      <MLTrainingCard controller={controller} />
    </ModuleCard>
  );
}

function BuildingSystemToggle({
  card,
  controlActive,
  loadingCard,
  onToggle,
  canToggleControl,
}: {
  card: BuildingSystemCard;
  controlActive: boolean;
  loadingCard: boolean;
  onToggle: (card: FeatureToggleCard) => void;
  canToggleControl: boolean;
}) {
  if (!card.controlModule) return null;

  return (
    <div className="mt-2 flex items-center gap-2">
      <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Control:</span>
      <button
        onClick={() => onToggle({ id: card.id, label: `${card.label} Control`, moduleType: card.controlModule!, description: "" })}
        disabled={loadingCard || !canToggleControl}
        className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
        style={{
          background: controlActive ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
          border: `1px solid ${controlActive ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
          cursor: !canToggle ? "not-allowed" : "pointer",
          opacity: !canToggle ? 0.6 : 1,
        }}
        aria-label={`Toggle ${card.label} control`}
        type="button"
      >
        <span className="inline-block h-3 w-3 rounded-full bg-white transition-transform" style={{ transform: controlActive ? "translateX(17px)" : "translateX(2px)" }} />
      </button>
    </div>
  );
}

function BuildingSystemsCard({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  const buildingSystemCards = getBuildingSystemCards(controller.availableModules);
  const canToggleControl = controller.canToggleControl ?? false;

  return (
    <ModuleCard description="Monitoring always on. Toggle control features per discipline." icon={<Gauge className="h-5 w-5" />} title="Building Systems">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {buildingSystemCards.map((card) => {
          const controlActive = card.controlModule ? controller.isModuleActive(card.controlModule) : false;
          const loadingCard = controller.togglingCardId === card.id;
          return (
            <div key={card.id} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: loadingCard ? 0.75 : 1 }}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{card.label}</h3>
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
                      Monitoring
                    </span>
                  </div>
                  <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
                  <BuildingSystemToggle
                    card={card}
                    controlActive={controlActive}
                    loadingCard={loadingCard}
                    onToggle={controller.toggleCard}
                    canToggleControl={canToggleControl}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </ModuleCard>
  );
}

function AddonsCard({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  const addonCards = getAddonToggleCards(controller.availableModules);

  return (
    <div className="glass-panel overflow-hidden" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ background: "rgba(168, 85, 247, 0.15)", color: "rgb(168, 85, 247)" }}>
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Add-ons</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Standalone features you can enable or disable</p>
          </div>
        </div>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {addonCards.map((card) => {
            const active = controller.isModuleActive(card.moduleType);
            const loadingCard = controller.togglingCardId === card.id;
            return (
              <div key={card.id} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: loadingCard ? 0.75 : 1 }}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{card.label}</h3>
                    <p className="mt-1 text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
                  </div>
                  <button
                    onClick={() => void controller.handleFeatureToggle(card)}
                    disabled={loadingCard || !controller.canToggleModules}
                    className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
                    style={{
                      background: active ? "var(--color-sentinel-green)" : "var(--color-sentinel-bg-hover)",
                      border: `1px solid ${active ? "var(--color-sentinel-green)" : "var(--glass-border)"}`,
                      cursor: !controller.canToggleModules ? "not-allowed" : "pointer",
                      opacity: !controller.canToggleModules ? 0.6 : 1,
                    }}
                    aria-label={`Toggle ${card.label}`}
                    type="button"
                  >
                    <span className="inline-block h-4 w-4 rounded-full bg-white transition-transform" style={{ transform: active ? "translateX(22px)" : "translateX(2px)" }} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        {!controller.canToggleModules ? (
          <div className="mt-4 rounded-lg p-3" style={{ background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.25)" }}>
            <p className="text-xs" style={{ color: "var(--color-sentinel-amber)" }}>
              {controller.currentUserRole !== "admin" && !controller.settingsPageUnlocked
                ? "Unlock settings at the top of the page to toggle modules."
                : "You have read-only access. Contact an administrator to request module changes."}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ModuleAccessSections({
  controller,
  onError,
}: {
  controller: ReturnType<typeof useSettingsController>;
  onError?: (error: string) => void;
}) {
  return (
    <>
      <PlatformModuleCard controller={controller} />
      <BuildingSystemsCard controller={controller} />
      <ModuleDescriptions onError={onError} />
      <AddonsCard controller={controller} />
    </>
  );
}
