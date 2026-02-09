/**
 * Modules Package - Bolt-on Module System Components
 *
 * Central hub for module management and cross-system AI integration.
 */

export { AIRecommendationsPanel } from './AIRecommendationsPanel';
export { ModuleSelector } from './ModuleSelector';
export { ModularDashboard } from './ModularDashboard';
export { IntegrationStatusBar } from './IntegrationStatusBar';

// Re-export context and hooks
export {
  ModuleProvider,
} from '../../contexts/ModuleContext';

export {
  useModules,
  useModuleActive,
  useCriticalRecommendations,
  useCrossSystemRecommendations,
  useModuleRecommendations,
} from '../../contexts/ModuleHooks';

// Re-export types
export type {
  ModuleType,
  ModuleStatus,
  ModuleDefinition,
  ModuleInstance,
  AIRecommendation,
  IntegrationSummary,
  RecommendationType,
  RecommendationPriority,
} from '../../lib/moduleRegistry';

export { moduleRegistryApi, MODULE_COLORS, MODULE_ICONS, PRIORITY_COLORS } from '../../lib/moduleRegistry';
