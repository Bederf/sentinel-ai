import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronRight, Cpu, Link, Sparkles } from "lucide-react";
import { modulesApi } from "../../lib/api/modules";
import type { ModuleDefinition } from "../../lib/api/modules";

interface ModuleDescriptionsProps {
  onError?: (error: string) => void;
}

export function ModuleDescriptions({ onError }: ModuleDescriptionsProps) {
  const [modules, setModules] = useState<ModuleDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedModule, setExpandedModule] = useState<string | null>(null);

  const fetchModules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await modulesApi.getAvailableModules();
      setModules(data);
    } catch {
      onError?.("Failed to load module definitions");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchModules();
  }, [fetchModules]);

  if (loading) {
    return (
      <div className="glass-panel flat overflow-hidden">
        <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
              <Cpu className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Module Details</h2>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!modules.length) return null;

  return (
    <div className="glass-panel flat overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(59, 130, 246, 0.15)", color: "var(--color-sentinel-blue)" }}>
            <Cpu className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Module Details</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Capabilities, AI features, and integrations for each module
            </p>
          </div>
        </div>
      </div>

      <div className="p-4">
        <div className="space-y-1">
          {modules.map((mod) => {
            const isExpanded = expandedModule === mod.module_type;
            const hasDetails = (mod.capabilities && mod.capabilities.length > 0) ||
              (mod.ai_features && mod.ai_features.length > 0) ||
              (mod.integrates_with && mod.integrates_with.length > 0);

            return (
              <div key={mod.module_type}>
                <button
                  type="button"
                  onClick={() => hasDetails ? setExpandedModule(isExpanded ? null : mod.module_type) : undefined}
                  className="w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors"
                  style={{
                    background: isExpanded ? "var(--color-sentinel-bg-secondary)" : "transparent",
                    cursor: hasDetails ? "pointer" : "default",
                  }}
                >
                  {hasDetails ? (
                    isExpanded ? <ChevronDown className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-blue)" }} />
                      : <ChevronRight className="h-4 w-4 flex-shrink-0" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                  ) : (
                    <div className="w-4" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {mod.name}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(59, 130, 246, 0.1)", color: "var(--color-sentinel-blue)" }}>
                        v{mod.version}
                      </span>
                    </div>
                    <p className="text-xs mt-0.5 truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {mod.description}
                    </p>
                  </div>
                </button>

                {isExpanded && hasDetails && (
                  <div
                    className="ml-7 mb-2 p-3 rounded-lg space-y-3"
                    style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}
                  >
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
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
