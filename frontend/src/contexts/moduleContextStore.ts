import { createContext } from "react";
import type {
  AIRecommendation,
  IntegrationSummary,
  ModuleDefinition,
  ModuleInstance,
  ModuleType,
} from "../lib/moduleRegistry";

export interface ModuleContextValue {
  siteId: string | null;
  siteName: string | null;
  activeModules: ModuleInstance[];
  availableModules: ModuleDefinition[];
  recommendations: AIRecommendation[];
  integrationSummary: IntegrationSummary | null;
  loading: boolean;
  error: string | null;
  setSite: (siteId: string, siteName: string) => void;
  activateModule: (moduleType: ModuleType, config?: Record<string, unknown>) => Promise<void>;
  deactivateModule: (moduleType: ModuleType) => Promise<void>;
  isModuleActive: (moduleType: ModuleType) => boolean;
  addRecommendation: (
    recommendation: Omit<AIRecommendation, "recommendation_id" | "timestamp" | "acknowledged" | "resolved">
  ) => void;
  acknowledgeRecommendation: (recommendationId: string) => Promise<void>;
  resolveRecommendation: (recommendationId: string) => Promise<void>;
  refreshIntegration: () => Promise<void>;
  refreshRecommendations: () => Promise<void>;
  getActiveIntegrations: () => { source: ModuleType; target: ModuleType; name: string }[];
  canIntegrateWith: (moduleType: ModuleType) => ModuleType[];
}

export const ModuleContext = createContext<ModuleContextValue | undefined>(undefined);
