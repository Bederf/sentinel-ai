/* eslint-disable react-refresh/only-export-components */
/**
 * Building Page Section Definitions
 *
 * Centralized definitions for all toggleable sections on the building detail page.
 * Used by CardLibrary to show/hide sections via on/off toggles.
 *
 * Section IDs match the intelligence cards rendered in the overview tab.
 */

import type { ReactNode } from 'react';
import {
  Brain,
  Cpu,
  Sun,
  Activity,
  Lightbulb,
  Users,
  Zap,
  Thermometer,
  Droplets,
  Flame,
  Shield,
} from 'lucide-react';

// Card definition with metadata
export interface CardDefinition {
  id: string;
  name: string;
  description: string;
  icon: ReactNode;
  category: 'kpi' | 'section';
  defaultVisible: boolean;
}

// KPI Card definitions (top row — 4 metric cards)
export const KPI_CARDS: CardDefinition[] = [
  {
    id: 'kpi-equipment',
    name: 'Equipment',
    description: 'Total equipment count',
    icon: <Cpu className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-alerts',
    name: 'Active Alerts',
    description: 'Current alerts and warnings',
    icon: <Activity className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-health',
    name: 'Avg Health',
    description: 'Average equipment health score',
    icon: <Activity className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  },
  {
    id: 'kpi-predictions',
    name: 'Predictions',
    description: 'AI-detected risk predictions',
    icon: <Shield className="w-4 h-4" />,
    category: 'kpi',
    defaultVisible: true
  }
];

// Section definitions — building overview intelligence cards
// Order matches render order on the building page
export const SECTION_CARDS: CardDefinition[] = [
  {
    id: 'ai-optimization',
    name: 'AI Optimization',
    description: 'Optimization status, mode toggle, and pending recommendations',
    icon: <Brain className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'hvac-intelligence',
    name: 'HVAC Intelligence',
    description: 'Climate control health, thermal runway, and zone status',
    icon: <Thermometer className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'energy-intelligence',
    name: 'Energy Intelligence',
    description: 'Optimisation savings, mode, and applied recommendations',
    icon: <Zap className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'solar-intelligence',
    name: 'Solar & BESS Intelligence',
    description: 'Generation, self-consumption, and performance ratio',
    icon: <Sun className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'water-intelligence',
    name: 'Water Intelligence',
    description: 'Consumption vs baseline, leak alerts, and peak flow',
    icon: <Droplets className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'fire-intelligence',
    name: 'Fire Safety Intelligence',
    description: 'Equipment compliance, system status, and overdue items',
    icon: <Flame className="w-4 h-4" />,
    category: 'section',
    defaultVisible: true
  },
  {
    id: 'security-intelligence',
    name: 'Security Intelligence',
    description: 'Access control zones, cameras, and occupancy',
    icon: <Shield className="w-4 h-4" />,
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
  },
];

// All cards combined
export const ALL_CARDS = [...KPI_CARDS, ...SECTION_CARDS];

// Default KPI card IDs
export const DEFAULT_KPI_CARDS = KPI_CARDS.map(c => c.id);

// Default section IDs
export const DEFAULT_SECTIONS = SECTION_CARDS.map(c => c.id);
