/* eslint-disable react-refresh/only-export-components */
/**
 * Dashboard Card Definitions
 *
 * Centralized definitions for all dashboard cards with metadata.
 * Used by CardLibrary and Dashboard components.
 */

import {
  Building2,
  Cpu,
  Bell,
  DollarSign,
  Shield,
  BarChart3,
  Activity,
  Sun,
  Leaf,
  Lightbulb,
  AlertCircle,
  Users,
} from 'lucide-react';

// Card definition with metadata
export interface CardDefinition {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  category: 'kpi' | 'section';
  defaultVisible: boolean;
}

// KPI Card definitions
export const KPI_CARDS: CardDefinition[] = [
  {
    id: 'kpi-protected-sites',
    name: 'Protected Sites',
    description: 'Total sites under SENTINEL protection',
    icon: <Building2 className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-monitored-assets',
    name: 'Monitored Assets',
    description: 'Total equipment being monitored',
    icon: <Cpu className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-active-risks',
    name: 'Active Risks',
    description: 'Current alerts and warnings',
    icon: <Bell className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-potential-savings',
    name: 'Potential Savings',
    description: 'Estimated savings from preventive actions',
    icon: <DollarSign className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-risk-predictions',
    name: 'Risk Predictions',
    description: 'AI-detected risk events count',
    icon: <Shield className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  }
];

// Section definitions
export const SECTION_CARDS: CardDefinition[] = [
  {
    id: 'kpi-row',
    name: 'KPI Overview',
    description: 'Top-level metrics and statistics',
    icon: <Activity className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'site-protection',
    name: 'Site Protection',
    description: 'Site status grid with protection levels',
    icon: <Building2 className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'energy-analytics',
    name: 'Energy Analytics',
    description: 'Energy consumption charts and trends',
    icon: <BarChart3 className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'risk-predictions',
    name: 'Risk Intelligence',
    description: 'AI predictions and ROI analysis',
    icon: <Shield className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'solar-bess',
    name: 'Solar & BESS',
    description: 'Solar generation, battery storage, inverter fleet, and energy flow',
    icon: <Sun className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'energy-comparison',
    name: 'Energy Impact Comparison',
    description: 'Multi-tier energy savings comparison (Baseline vs Lighting vs SENTINEL)',
    icon: <Leaf className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'energy-comparison-actual-vs-sentinel',
    name: 'Actual vs SENTINEL Energy',
    description: 'Side-by-side real energy consumption vs AI-optimized predictions',
    icon: <BarChart3 className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'solar-annual',
    name: 'Solar Annual Summary',
    description: '365-day annual simulation with AI savings progression (2%-18%)',
    icon: <Sun className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'comfort-assistant',
    name: 'Comfort Assistant',
    description: 'AI-powered comfort recommendations and occupancy insights',
    icon: <Users className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'occupancy-dashboard',
    name: 'Occupancy Dashboard',
    description: 'Real-time occupancy tracking and patterns',
    icon: <Users className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'lighting-intelligence',
    name: 'Lighting Intelligence',
    description: 'AI-powered lighting optimization and zone control',
    icon: <Lightbulb className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  }
];

// All cards combined
export const ALL_CARDS = [...KPI_CARDS, ...SECTION_CARDS];

// Default KPI card IDs
export const DEFAULT_KPI_CARDS = KPI_CARDS.map(c => c.id);

// Default section IDs
export const DEFAULT_SECTIONS = SECTION_CARDS.map(c => c.id);
