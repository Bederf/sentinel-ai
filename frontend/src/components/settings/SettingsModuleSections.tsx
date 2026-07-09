import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, ChevronRight, Cpu, Gauge, Link, Sparkles } from "lucide-react";
import {
  getAddonToggleCards,
  getBuildingSystemCards,
  getPlatformStatusCards,
  type BuildingSystemCard,
  type FeatureToggleCard,
} from "./settingsCatalog";
import type { useSettingsController } from "./useSettingsController";
import type { ModuleDefinition } from "../../lib/api/modules";
import { AegisSettings } from "./AegisSettings";

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
    <div className="glass-panel flat overflow-hidden">
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

function ModuleExpandedDetails({ mod }: { mod: ModuleDefinition }) {
  const hasDetails = (mod.capabilities && mod.capabilities.length > 0) ||
    (mod.ai_features && mod.ai_features.length > 0) ||
    (mod.integrates_with && mod.integrates_with.length > 0);

  if (!hasDetails) return null;

  return (
    <div className="mt-3 p-3 rounded-lg space-y-3" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
      {mod.capabilities && mod.capabilities.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold mb-1.5" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Capabilities
          </h4>
          <div className="space-y-1">
            {mod.capabilities.map((cap) => (
              <div key={cap.id} className="flex items-start gap-2">
                <div className="h-1.5 w-1.5 rounded-full mt-1.5 flex-shrink-0" style={{ background: "var(--color-sentinel-green)" }} />
                <div>
                  <span className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {cap.name}
                  </span>
                  <span className="text-xs ml-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    — {cap.description}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {mod.ai_features && mod.ai_features.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold mb-1.5 flex items-center gap-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
            <Sparkles className="h-3 w-3" style={{ color: "rgb(168, 85, 247)" }} />
            AI Features
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {mod.ai_features.map((feat) => (
              <span
                key={feat}
                className="text-[10px] px-2 py-0.5 rounded-full"
                style={{ background: "rgba(168, 85, 247, 0.15)", color: "rgb(168, 85, 247)" }}
              >
                {feat.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {mod.integrates_with && mod.integrates_with.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold mb-1.5 flex items-center gap-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
            <Link className="h-3 w-3" style={{ color: "var(--color-sentinel-blue)" }} />
            Integrates With
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {mod.integrates_with.map((int_mod) => (
              <span
                key={int_mod}
                className="text-[10px] px-2 py-0.5 rounded-full"
                style={{ background: "rgba(59, 130, 246, 0.1)", color: "var(--color-sentinel-blue)" }}
              >
                {int_mod.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ModulesCard({ controller }: { controller: ReturnType<typeof useSettingsController> }) {
  const [expandedModule, setExpandedModule] = useState<string | null>(null);
  const platformCards = getPlatformStatusCards(controller.availableModules);
  const addonCards = getAddonToggleCards(controller.availableModules);
  const modMap = new Map(controller.availableModules.map((m) => [m.module_type, m]));

  return (
    <ModuleCard
      description="Core platform modules and optional add-on features"
      icon={<Cpu className="h-5 w-5" />}
      title="Modules"
    >
      {/* Default modules */}
      {platformCards.length > 0 && (
        <div className="mb-6">
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Always Active
          </h3>
          <div className="space-y-1">
            {platformCards.map((card) => {
              const mod = modMap.get(card.moduleType);
              const isExpanded = expandedModule === card.id;
              const hasDetails = mod && ((mod.capabilities && mod.capabilities.length > 0) ||
                (mod.ai_features && mod.ai_features.length > 0) ||
                (mod.integrates_with && mod.integrates_with.length > 0));

              return (
                <div key={card.id} className="rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                  <button
                    type="button"
                    onClick={() => hasDetails ? setExpandedModule(isExpanded ? null : card.id) : undefined}
                    className="w-full flex items-center gap-3 p-3 text-left"
                  >
                    {hasDetails ? (
                      isExpanded ? <ChevronDown className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-blue)" }} />
                        : <ChevronRight className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                    ) : (
                      <div className="w-4" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          {card.label}
                        </span>
                      </div>
                      <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {card.description}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium flex-shrink-0" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
                      Active
                    </div>
                  </button>
                  {isExpanded && mod && <div className="px-3 pb-3"><ModuleExpandedDetails mod={mod} /></div>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Addon modules */}
      {addonCards.length > 0 && (
        <div className="mb-6">
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Optional Add-ons
          </h3>
          <div className="space-y-1">
            {addonCards.map((card) => {
              const active = controller.isModuleActive(card.moduleType);
              const loadingCard = controller.togglingCardId === card.id;
              const mod = modMap.get(card.moduleType);
              const isExpanded = expandedModule === card.id;
              const hasDetails = mod && ((mod.capabilities && mod.capabilities.length > 0) ||
                (mod.ai_features && mod.ai_features.length > 0) ||
                (mod.integrates_with && mod.integrates_with.length > 0));

              return (
                <div key={card.id} className="rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: loadingCard ? 0.75 : 1 }}>
                  <div className="flex items-center gap-3 p-3">
                    {hasDetails ? (
                      <button
                        type="button"
                        onClick={() => setExpandedModule(isExpanded ? null : card.id)}
                        className="flex-shrink-0"
                      >
                        {isExpanded ? <ChevronDown className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
                          : <ChevronRight className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />}
                      </button>
                    ) : (
                      <div className="w-4 flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {card.label}
                      </span>
                      <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                        {card.description}
                      </p>
                    </div>
                    <button
                      onClick={() => void controller.handleFeatureToggle(card)}
                      disabled={loadingCard || !controller.canToggleModules}
                      className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0"
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
                  {isExpanded && mod && <div className="px-3 pb-3"><ModuleExpandedDetails mod={mod} /></div>}
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
      )}

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
          cursor: !canToggleControl ? "not-allowed" : "pointer",
          opacity: !canToggleControl ? 0.6 : 1,
        }}
        aria-label={`Toggle ${card.label} control`}
        type="button"
      >
        <span className="inline-block h-3 w-3 rounded-full bg-white transition-transform" style={{ transform: controlActive ? "translateX(17px)" : "translateX(2px)" }} />
      </button>
    </div>
  );
}

function BuildingSystemsCard({ controller, onError }: { controller: ReturnType<typeof useSettingsController>; onError?: (error: string) => void }) {
  const [expandedModule, setExpandedModule] = useState<string | null>(null);
  const buildingSystemCards = getBuildingSystemCards(controller.availableModules, controller);
  const canToggleControl = controller.canToggleControl ?? false;
  const modMap = new Map(controller.availableModules.map((m) => [m.module_type, m]));

  return (
    <ModuleCard description="Licensed monitoring per discipline. Toggle control features separately." icon={<Gauge className="h-5 w-5" />} title="Building Systems">
      <div className="space-y-1">
        {buildingSystemCards.map((card) => {
          const controlActive = card.controlModule ? controller.isModuleActive(card.controlModule) : false;
          const loadingCard = controller.togglingCardId === card.id;
          const mod = modMap.get(card.baseModule);
          const isExpanded = expandedModule === card.id;
          const hasDetails = mod && ((mod.capabilities && mod.capabilities.length > 0) ||
            (mod.ai_features && mod.ai_features.length > 0) ||
            (mod.integrates_with && mod.integrates_with.length > 0));

          return (
            <div key={card.id} className="rounded-lg" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)", opacity: loadingCard ? 0.75 : 1 }}>
              <button
                type="button"
                onClick={() => hasDetails ? setExpandedModule(isExpanded ? null : card.id) : undefined}
                className="w-full flex items-center gap-3 p-3 text-left"
              >
                {hasDetails ? (
                  isExpanded ? <ChevronDown className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-blue)" }} />
                    : <ChevronRight className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                ) : (
                  <div className="w-4 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {card.label}
                    </span>
                    {card.licensed ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
                        Licensed
                      </span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ background: "rgba(107, 114, 128, 0.15)", color: "var(--color-sentinel-text-disabled)" }}>
                        Not Licensed
                      </span>
                    )}
                  </div>
                  <p className="text-xs mt-0.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>{card.description}</p>
                  <BuildingSystemToggle
                    card={card}
                    controlActive={controlActive}
                    loadingCard={loadingCard}
                    onToggle={controller.handleFeatureToggle}
                    canToggleControl={canToggleControl}
                  />
                </div>
              </button>
              {isExpanded && mod && <div className="px-3 pb-3"><ModuleExpandedDetails mod={mod} /></div>}
            </div>
          );
        })}
      </div>

      <div className="mt-6" style={{ height: "1px", background: "var(--color-sentinel-border)" }} />

      <div className="mt-6">
        <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          BESS Control
        </h3>
        <AegisSettings
          key={`aegis-${controller.selectedSiteId}`}
          siteId={controller.selectedSiteId ?? undefined}
          currentUserRole={controller.currentUserRole}
          readOnly={controller.readOnly}
          onError={onError}
          onSuccess={controller.handleSuccess}
          embedded
        />
      </div>
    </ModuleCard>
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
      <ModulesCard controller={controller} />
      <BuildingSystemsCard controller={controller} onError={onError} />
    </>
  );
}
