/**
 * Card Definitions
 *
 * Defines default KPI cards and dashboard sections visibility
 * Sections can be filtered by module access via getModuleFilteredSections()
 */
import type { LucideIcon } from 'lucide-react';
import type { ModuleType } from './moduleRegistry';

export interface CardDefinition {
  id: string;
  name: string;
  description?: string;
  requiredModules?: ModuleType[];  // Optional module requirement for visibility
}

// KPI Card definitions
export const KPI_CARDS: CardDefinition[] = [
  { id: 'kpi-protected-sites', name: 'Protected Sites', description: 'Number of sites under protection' },
  { id: 'kpi-monitored-assets', name: 'Monitored Assets', description: 'Total equipment being monitored' },
  { id: 'kpi-active-risks', name: 'Active Risks', description: 'Current active risk alerts' },
  { id: 'kpi-potential-savings', name: 'Potential Savings', description: 'Savings from preventive actions' },
  { id: 'kpi-risk-predictions', name: 'Risk Predictions', description: 'AI-detected risk events' },
];

// Dashboard Section definitions with module requirements
export const SECTION_CARDS: CardDefinition[] = [
  { id: 'kpi-row', name: 'KPI Row', description: 'Key performance indicators', requiredModules: [] },
  { id: 'site-protection', name: 'Site Protection', description: 'Site protection status', requiredModules: [] },
  { id: 'lighting-intelligence', name: 'Lighting Intelligence', description: 'Lighting optimization', requiredModules: ['lighting'] },
  { id: 'solar-bess', name: 'Solar & BESS', description: 'Solar and battery status', requiredModules: ['solar'] },
  { id: 'solar-annual', name: 'Solar Annual', description: 'Annual solar summary', requiredModules: ['solar'] },
  { id: 'energy-analytics', name: 'Energy Analytics', description: 'Energy consumption data', requiredModules: [] },
  { id: 'energy-comparison', name: 'Energy Comparison', description: 'Energy comparison metrics', requiredModules: [] },
  { id: 'energy-comparison-actual-vs-sentinel', name: 'Actual vs SENTINEL', description: 'Actual vs SENTINEL energy', requiredModules: [] },
  { id: 'risk-predictions', name: 'Risk Predictions Panel', description: 'AI risk predictions', requiredModules: [] },
  { id: 'comfort-assistant', name: 'Comfort Assistant', description: 'Comfort optimization', requiredModules: ['hvac'] },
  { id: 'occupancy-dashboard', name: 'Occupancy', description: 'Occupancy monitoring', requiredModules: ['lighting'] },
  { id: 'power-meter-validation', name: 'Power Meter Validation', description: 'Real-time HVAC anomaly detection', requiredModules: [] },
  { id: 'cost-validation', name: 'Cost Validation', description: 'Monthly cost reconciliation', requiredModules: [] },
];

// Default visible KPI cards on dashboard load
export const DEFAULT_KPI_CARDS = [
  'kpi-protected-sites',
  'kpi-monitored-assets',
  'kpi-active-risks',
  'kpi-potential-savings',
  'kpi-risk-predictions',
];

// Default visible dashboard sections on load
// Site-specific panels (lighting, solar, BESS, energy comparison, risk predictions,
// comfort, occupancy, validation) now live in SiteDetail.tsx.
export const DEFAULT_SECTIONS = [
  'kpi-row',
  'site-protection',
  'energy-analytics',
];

/**
 * Filter sections based on active modules
 * Returns only sections that have no module requirement, or where the user has the required module
 */
export function getModuleFilteredSections(
  sections: string[],
  isModuleActive: (module: ModuleType) => boolean
): string[] {
  return sections.filter(sectionId => {
    const section = SECTION_CARDS.find(s => s.id === sectionId);
    if (!section || !section.requiredModules || section.requiredModules.length === 0) {
      return true;  // No requirement = show it
    }
    // Show section if ANY required module is active
    return section.requiredModules.some(module => isModuleActive(module));
  });
}

/**
 * Get demo-specific default dashboard cards and sections
 * Tailors the default view for each demo user
 */
export function getDemoDefaultCards(email: string): {
  kpiCards: string[];
  sections: string[];
} {
  // All demo users get full access — users manage visibility from settings page
  return {
    kpiCards: DEFAULT_KPI_CARDS,
    sections: DEFAULT_SECTIONS,
  };
}
