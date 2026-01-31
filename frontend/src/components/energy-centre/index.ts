/**
 * Energy Centre Module - Bolt-on Package
 *
 * This module provides complete energy centre monitoring:
 * - Generator SCADA
 * - ATS monitoring
 * - Power metering
 * - UPS status
 * - Single-line diagram
 *
 * Can operate standalone or integrate with other modules (HVAC, Security)
 */

export { EnergyCentreDashboard } from './EnergyCentreDashboard';
export { GeneratorSynoptic } from './GeneratorSynoptic';
export { SingleLineDiagram } from './SingleLineDiagram';
export { PowerMeteringCard } from './PowerMeteringCard';
export { UPSStatusPanel } from './UPSStatusPanel';
export { ATSStatusPanel } from './ATSStatusPanel';

// Re-export API types for convenience
export type {
  Generator,
  GeneratorGroup,
  GeneratorHealth,
  DieselTank,
  ATSUnit,
  MVIncomer,
  Transformer,
  LVSwitchboard,
  PowerMeter,
  PFCBank,
  UPSSystem,
  SCADAOverview,
  SLDData,
} from '../../lib/energyCentreApi';

export { generatorApi, energyCentreApi } from '../../lib/energyCentreApi';

// Module metadata
export const moduleInfo = {
  id: 'energy',
  name: 'Energy Centre',
  version: '1.0.0',
  description: 'Generator, power metering, UPS, and electrical distribution monitoring',
  dependencies: [],
  integrates_with: ['hvac', 'security'],
  features: [
    'generator_monitoring',
    'ats_control',
    'power_metering',
    'ups_monitoring',
    'predictive_maintenance',
    'load_shedding_optimization',
  ],
};
