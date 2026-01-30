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
  Activity
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
  }
];

// All cards combined
export const ALL_CARDS = [...KPI_CARDS, ...SECTION_CARDS];

// Default KPI card IDs
export const DEFAULT_KPI_CARDS = KPI_CARDS.map(c => c.id);

// Default section IDs
export const DEFAULT_SECTIONS = SECTION_CARDS.map(c => c.id);
