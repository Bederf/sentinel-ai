import { useContext } from "react";
import type { AIRecommendation, ModuleType } from "../lib/moduleRegistry";
import { ModuleContext } from "./moduleContextStore";

export function useModules() {
  const context = useContext(ModuleContext);
  if (!context) {
    throw new Error("useModules must be used within a ModuleProvider");
  }
  return context;
}

export function useModuleActive(moduleType: ModuleType): boolean {
  const { isModuleActive } = useModules();
  return isModuleActive(moduleType);
}

export function useCriticalRecommendations(): AIRecommendation[] {
  const { recommendations } = useModules();
  return recommendations.filter((r) => r.priority === "critical" && !r.resolved);
}

export function useCrossSystemRecommendations(): AIRecommendation[] {
  const { recommendations } = useModules();
  return recommendations.filter((r) => r.recommendation_type === "cross_system" && !r.resolved);
}

export function useModuleRecommendations(moduleType: ModuleType): AIRecommendation[] {
  const { recommendations } = useModules();
  return recommendations.filter(
    (r) => (r.source_module === moduleType || r.related_modules.includes(moduleType)) && !r.resolved
  );
}
