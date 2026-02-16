/**
 * Card Definitions
 * 
 * Defines default KPI cards and dashboard sections visibility
 */
import type { LucideIcon } from 'lucide-react';

export interface CardDefinition {
  id: string;
  name: string;
  description?: string;
}

// KPI Card definitions
export const KPI_CARDS: CardDefinition[] = [
  { id: 'kpi-protected-sites', name: 'Protected Sites', description: 'Number of sites under protection' },
  { id: 'kpi-monitored-assets', name: 'Monitored Assets', description: 'Total equipment being monitored' },
  { id: 'kpi-active-risks', name: 'Active Risks', description: 'Current active risk alerts' },
  { id: 'kpi-potential-savings', name: 'Potential Savings', description: 'Savings from preventive actions' },
  { id: 'kpi-risk-predictions', name: 'Risk Predictions', description: 'AI-detected risk events' },
];

// Dashboard Section definitions
export const SECTION_CARDS: CardDefinition[] = [
  { id: 'kpi-row', name: 'KPI Row', description: 'Key performance indicators' },
  { id: 'site-protection', name: 'Site Protection', description: 'Site protection status' },
  { id: 'lighting-intelligence', name: 'Lighting Intelligence', description: 'Lighting optimization' },
  { id: 'solar-bess', name: 'Solar & BESS', description: 'Solar and battery status' },
  { id: 'solar-annual', name: 'Solar Annual', description: 'Annual solar summary' },
  { id: 'energy-analytics', name: 'Energy Analytics', description: 'Energy consumption data' },
  { id: 'energy-comparison', name: 'Energy Comparison', description: 'Energy comparison metrics' },
  { id: 'energy-comparison-actual-vs-sentinel', name: 'Actual vs SENTINEL', description: 'Actual vs SENTINEL energy' },
  { id: 'risk-predictions', name: 'Risk Predictions', description: 'AI risk predictions' },
  { id: 'comfort-assistant', name: 'Comfort Assistant', description: 'Comfort optimization' },
  { id: 'occupancy-dashboard', name: 'Occupancy', description: 'Occupancy monitoring' },
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
export const DEFAULT_SECTIONS = [
  'kpi-row',
  'site-protection',
  'lighting-intelligence',
  'solar-bess',
  'solar-annual',
  'energy-analytics',
  'energy-comparison',
  'energy-comparison-actual-vs-sentinel',
  'risk-predictions',
  'comfort-assistant',
  'occupancy-dashboard',
];
