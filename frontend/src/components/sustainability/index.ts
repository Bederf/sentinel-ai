/**
 * Sustainability & ESG Module - Bolt-on Package
 *
 * Carbon emissions tracking, efficiency benchmarks, and Green Star SA certification.
 * Derives all data from existing Energy module consumption data.
 */

export { SustainabilityDashboard } from './SustainabilityDashboard';

// Re-export API types for convenience
export type {
  EmissionsSnapshot,
  EmissionsHistory,
  EmissionsBreakdown,
  GreenStarCategory,
  GreenStarAssessment,
  EfficiencyMetrics,
  SustainabilitySummary,
  SustainabilityConfig,
} from '../../lib/sustainabilityApi';

export { sustainabilityApi } from '../../lib/sustainabilityApi';

// Module metadata
export const moduleInfo = {
  id: 'sustainability',
  name: 'Sustainability & ESG',
  version: '1.0.0',
  description: 'Carbon emissions tracking, efficiency benchmarks, and Green Star SA certification',
  dependencies: ['energy'],
  integrates_with: ['energy', 'hvac', 'lighting'],
  features: [
    'emissions_tracking',
    'efficiency_metrics',
    'green_star_sa',
    'esg_reporting',
    'benchmark_comparison',
  ],
};
