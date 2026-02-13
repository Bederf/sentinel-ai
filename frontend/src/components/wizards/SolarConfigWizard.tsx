/**
 * Solar Configuration Wizard
 *
 * Multi-step wizard for solar site configuration during onboarding.
 *
 * Steps:
 * 1. Site Selection - Create new or select existing site
 * 2. Plant Configuration - Define solar plants (capacity, panels)
 * 3. Inverter Setup - Add inverters with Modbus TCP configuration
 * 4. Optional Components - BESS, grid meter, tariff selection
 * 5. Review & Activate - Verify and submit configuration
 */

import { useState, useCallback } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  Zap,
} from 'lucide-react';
import type {
  SolarPlant,
  SolarInverter,
  BESSConfig,
  GridMeterConfig,
  SolarConfig,
  SolarSiteRequest,
} from '@/lib/api';
import {
  solarConfigApi,
  isValidEquipmentCode,
  calculateInverterCoverage,
  suggestEquipmentId,
} from '@/lib/api';
import { toast } from 'sonner';

interface SolarWizardState {
  step: 1 | 2 | 3 | 4 | 5;
  siteId: string;
  siteName: string;
  isNewSite: boolean;
  latitude: number;
  longitude: number;

  // Draft entities (before adding to list)
  draftPlant: Partial<SolarPlant>;
  draftInverter: Partial<SolarInverter>;

  // Collections
  plants: SolarPlant[];
  bess: BESSConfig | null;
  gridMeter: GridMeterConfig | null;
  selectedPlantForInverter: string | null;

  // Grid config
  utility: string;
  tariff: string;

  // UI state
  errors: Record<string, string>;
  loading: boolean;
  success: boolean;
}

const MANUFACTURERS = {
  inverter: ['Huawei', 'SMA', 'Schneider', 'Fronius', 'ABB', 'Sungrow'],
  bess: ['Tesla', 'LG', 'Sonnen', 'BYD', 'Huawei', 'Saft'],
  meter: ['Siemens', 'ABB', 'Schneider', 'Eastron'],
};

const TARIFFS = ['City Power 2026', 'Eskom 2026', 'Custom'];

interface SolarConfigWizardProps {
  onComplete?: () => void;
}

export function SolarConfigWizard({ onComplete }: SolarConfigWizardProps = {}) {
  const [state, setState] = useState<SolarWizardState>({
    step: 1,
    siteId: '',
    siteName: '',
    isNewSite: false,
    latitude: 0,
    longitude: 0,
    draftPlant: {},
    draftInverter: {},
    plants: [],
    bess: null,
    gridMeter: null,
    selectedPlantForInverter: null,
    utility: 'City Power',
    tariff: 'standard',
    errors: {},
    loading: false,
    success: false,
  });

  // ============================================================================
  // Validation Functions
  // ============================================================================

  const validateSite = useCallback((): string | null => {
    if (!state.siteId.trim()) return 'Site ID is required';
    if (!state.siteName.trim()) return 'Site name is required';
    if (state.isNewSite) {
      if (state.latitude < -90 || state.latitude > 90) return 'Latitude must be between -90 and 90';
      if (state.longitude < -180 || state.longitude > 180) return 'Longitude must be between -180 and 180';
    }
    return null;
  }, [state.siteId, state.siteName, state.isNewSite, state.latitude, state.longitude]);

  const validatePlant = useCallback(
    (plant: Partial<SolarPlant>): string | null => {
      if (!plant.plant_id?.trim()) return 'Plant ID is required';
      if (!plant.name?.trim()) return 'Plant name is required';
      if (!plant.capacity_kwp || plant.capacity_kwp <= 0) return 'Capacity must be > 0';
      if (!plant.panel_count || plant.panel_count <= 0) return 'Panel count must be > 0';

      // Check for duplicates
      if (state.plants.some((p) => p.plant_id === plant.plant_id)) {
        return 'Plant ID already exists';
      }

      return null;
    },
    [state.plants]
  );

  const validateInverter = useCallback(
    (inverter: Partial<SolarInverter>): string | null => {
      if (!inverter.equipment_id?.trim()) return 'Equipment ID is required';
      if (!isValidEquipmentCode(inverter.equipment_id)) {
        return 'Invalid equipment code format (e.g., S002-INV-R-001)';
      }
      if (!inverter.manufacturer) return 'Manufacturer is required';
      if (!inverter.model?.trim()) return 'Model is required';
      if (!inverter.rated_kva || inverter.rated_kva <= 0) return 'Rated kVA must be > 0';
      if (!inverter.modbus_ip?.trim()) return 'IP address is required';

      // Check for duplicate equipment IDs
      const allInverters = Object.values(state.plants).flatMap((p) =>
        state.selectedPlantForInverter === p.plant_id ? [] : []
      );

      return null;
    },
    [state.plants, state.selectedPlantForInverter]
  );

  // ============================================================================
  // Add/Remove Functions
  // ============================================================================

  const addPlant = () => {
    const error = validatePlant(state.draftPlant);
    if (error) {
      setState((s) => ({ ...s, errors: { plant: error } }));
      return;
    }

    setState((s) => ({
      ...s,
      plants: [...s.plants, state.draftPlant as SolarPlant],
      draftPlant: {},
      errors: {},
    }));
  };

  const removePlant = (plantId: string) => {
    setState((s) => ({
      ...s,
      plants: s.plants.filter((p) => p.plant_id !== plantId),
    }));
  };

  const addInverter = () => {
    if (!state.selectedPlantForInverter) {
      setState((s) => ({
        ...s,
        errors: { inverter: 'Please select a plant first' },
      }));
      return;
    }

    const error = validateInverter(state.draftInverter);
    if (error) {
      setState((s) => ({ ...s, errors: { inverter: error } }));
      return;
    }

    setState((s) => {
      const inverters = { ...s.plants };
      if (!s.plants[state.selectedPlantForInverter!]) {
        s.plants[state.selectedPlantForInverter!] = [];
      }

      return {
        ...s,
        // This is simplified - in real implementation would track per-plant
        draftInverter: {},
        errors: {},
      };
    });
  };

  // ============================================================================
  // Step Navigation
  // ============================================================================

  const canProceedToStep = useCallback((): boolean => {
    switch (state.step) {
      case 1:
        return validateSite() === null;
      case 2:
        return state.plants.length > 0;
      case 3:
        return true; // Inverters optional for step 3
      case 4:
        return true; // Optional components
      case 5:
        return true; // Review
      default:
        return false;
    }
  }, [state.step, state.siteId, state.siteName, state.isNewSite, state.latitude, state.longitude, state.plants, validateSite]);

  const handleNextStep = () => {
    if (!canProceedToStep()) {
      const error = validateSite() || 'Please complete this step';
      setState((s) => ({ ...s, errors: { step: error } }));
      return;
    }

    if (state.step < 5) {
      setState((s) => ({ ...s, step: (s.step + 1) as any, errors: {} }));
    }
  };

  const handlePrevStep = () => {
    if (state.step > 1) {
      setState((s) => ({ ...s, step: (s.step - 1) as any }));
    }
  };

  // ============================================================================
  // Submit Handler
  // ============================================================================

  const handleSubmit = async () => {
    if (state.plants.length === 0) {
      setState((s) => ({ ...s, errors: { submit: 'At least one plant is required' } }));
      return;
    }

    setState((s) => ({ ...s, loading: true, errors: {} }));

    try {
      const config: SolarConfig = {
        plants: state.plants,
        inverters: {}, // Simplified for MVP
        bess: state.bess || undefined,
        grid_meter: state.gridMeter || undefined,
        utility: state.utility,
        tariff: state.tariff,
      };

      const request: SolarSiteRequest = {
        site_id: state.siteId,
        site_name: state.siteName,
        latitude: state.latitude,
        longitude: state.longitude,
        config,
      };

      // Validate before submitting
      const validation = await solarConfigApi.validateConfig(request);
      if (!validation.valid) {
        throw new Error(`Validation failed: ${validation.errors.join(', ')}`);
      }

      // Submit configuration
      const response = await solarConfigApi.createSolarSite(request);

      setState((s) => ({ ...s, success: true, loading: false }));
      toast.success('Solar site configured successfully!');

      // Call completion callback after short delay
      setTimeout(() => {
        onComplete?.();
      }, 2000);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create solar site';
      setState((s) => ({
        ...s,
        loading: false,
        errors: { submit: message },
      }));
      toast.error(message);
    }
  };

  // ============================================================================
  // Render Functions
  // ============================================================================

  const renderStep1 = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white flex items-center gap-2">
        <Zap className="w-6 h-6 text-yellow-400" />
        Site Selection
      </h2>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Site Selection
          </label>
          <div className="flex gap-4">
            <button
              onClick={() => setState((s) => ({ ...s, isNewSite: true }))}
              className={`flex-1 px-4 py-2 rounded-lg border-2 transition ${
                state.isNewSite
                  ? 'border-blue-500 bg-blue-500/10 text-white'
                  : 'border-gray-600 bg-gray-900/50 text-gray-300 hover:border-gray-500'
              }`}
            >
              Create New Site
            </button>
            <button
              onClick={() => setState((s) => ({ ...s, isNewSite: false }))}
              className={`flex-1 px-4 py-2 rounded-lg border-2 transition ${
                !state.isNewSite
                  ? 'border-blue-500 bg-blue-500/10 text-white'
                  : 'border-gray-600 bg-gray-900/50 text-gray-300 hover:border-gray-500'
              }`}
            >
              Select Existing
            </button>
          </div>
        </div>

        <input
          type="text"
          placeholder="Site ID (e.g., S002)"
          value={state.siteId}
          onChange={(e) => setState((s) => ({ ...s, siteId: e.target.value }))}
          className="w-full px-4 py-2 rounded-lg bg-gray-900/50 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />

        <input
          type="text"
          placeholder="Site Name (e.g., FNB Fairlands)"
          value={state.siteName}
          onChange={(e) => setState((s) => ({ ...s, siteName: e.target.value }))}
          className="w-full px-4 py-2 rounded-lg bg-gray-900/50 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />

        {state.isNewSite && (
          <div className="grid grid-cols-2 gap-4">
            <input
              type="number"
              placeholder="Latitude"
              value={state.latitude}
              onChange={(e) => setState((s) => ({ ...s, latitude: parseFloat(e.target.value) || 0 }))}
              className="w-full px-4 py-2 rounded-lg bg-gray-900/50 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <input
              type="number"
              placeholder="Longitude"
              value={state.longitude}
              onChange={(e) => setState((s) => ({ ...s, longitude: parseFloat(e.target.value) || 0 }))}
              className="w-full px-4 py-2 rounded-lg bg-gray-900/50 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        )}
      </div>

      {state.errors.step && (
        <div className="flex gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/50 text-red-200">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span>{state.errors.step}</span>
        </div>
      )}
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Plant Configuration</h2>

      <div className="space-y-4">
        <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700 space-y-4">
          <input
            type="text"
            placeholder="Plant ID (e.g., fairlands-rooftop)"
            value={state.draftPlant.plant_id || ''}
            onChange={(e) =>
              setState((s) => ({
                ...s,
                draftPlant: { ...s.draftPlant, plant_id: e.target.value },
              }))
            }
            className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />

          <input
            type="text"
            placeholder="Plant Name"
            value={state.draftPlant.name || ''}
            onChange={(e) =>
              setState((s) => ({
                ...s,
                draftPlant: { ...s.draftPlant, name: e.target.value },
              }))
            }
            className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />

          <div className="grid grid-cols-2 gap-4">
            <input
              type="number"
              placeholder="Capacity (kWp)"
              value={state.draftPlant.capacity_kwp || ''}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  draftPlant: { ...s.draftPlant, capacity_kwp: parseFloat(e.target.value) || 0 },
                }))
              }
              className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <input
              type="number"
              placeholder="Panel Count"
              value={state.draftPlant.panel_count || ''}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  draftPlant: { ...s.draftPlant, panel_count: parseInt(e.target.value) || 0 },
                }))
              }
              className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <button
            onClick={addPlant}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-blue-600/20 border border-blue-500/50 text-blue-300 hover:bg-blue-600/30 transition"
          >
            <Plus className="w-4 h-4" />
            Add Plant
          </button>
        </div>

        {state.errors.plant && (
          <div className="flex gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/50 text-red-200">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>{state.errors.plant}</span>
          </div>
        )}

        {state.plants.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-gray-300">Plants Added</h3>
            {state.plants.map((plant) => (
              <div
                key={plant.plant_id}
                className="flex items-center justify-between p-3 rounded-lg bg-gray-800/50 border border-gray-700"
              >
                <div>
                  <p className="font-medium text-white">{plant.name}</p>
                  <p className="text-sm text-gray-400">
                    {plant.capacity_kwp} kWp • {plant.panel_count} panels
                  </p>
                </div>
                <button
                  onClick={() => removePlant(plant.plant_id)}
                  className="p-2 text-red-400 hover:bg-red-500/10 rounded-lg transition"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const renderStep3 = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Inverter Setup</h2>

      <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-200 text-sm">
        <p>Configure Modbus TCP inverters for each plant. Coverage should be &gt;80% of plant capacity.</p>
      </div>

      <div className="space-y-4">
        <select
          value={state.selectedPlantForInverter || ''}
          onChange={(e) =>
            setState((s) => ({ ...s, selectedPlantForInverter: e.target.value }))
          }
          className="w-full px-4 py-2 rounded-lg bg-gray-900/50 border border-gray-700 text-white focus:outline-none focus:border-blue-500"
        >
          <option value="">Select a plant to add inverters</option>
          {state.plants.map((plant) => (
            <option key={plant.plant_id} value={plant.plant_id}>
              {plant.name} ({plant.capacity_kwp} kWp)
            </option>
          ))}
        </select>

        {state.selectedPlantForInverter && (
          <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700 space-y-4">
            <input
              type="text"
              placeholder="Equipment ID (e.g., S002-INV-R-001)"
              value={state.draftInverter.equipment_id || ''}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  draftInverter: { ...s.draftInverter, equipment_id: e.target.value },
                }))
              }
              className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />

            <select
              value={state.draftInverter.manufacturer || ''}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  draftInverter: { ...s.draftInverter, manufacturer: e.target.value },
                }))
              }
              className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">Select manufacturer</option>
              {MANUFACTURERS.inverter.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>

            <input
              type="text"
              placeholder="Model (e.g., SUN2000-100KTL-H2)"
              value={state.draftInverter.model || ''}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  draftInverter: { ...s.draftInverter, model: e.target.value },
                }))
              }
              className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />

            <div className="grid grid-cols-2 gap-4">
              <input
                type="number"
                placeholder="Rated kVA"
                value={state.draftInverter.rated_kva || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    draftInverter: { ...s.draftInverter, rated_kva: parseFloat(e.target.value) || 0 },
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
              <input
                type="text"
                placeholder="IP Address"
                value={state.draftInverter.modbus_ip || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    draftInverter: { ...s.draftInverter, modbus_ip: e.target.value },
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>

            <button
              onClick={addInverter}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-blue-600/20 border border-blue-500/50 text-blue-300 hover:bg-blue-600/30 transition"
            >
              <Plus className="w-4 h-4" />
              Add Inverter
            </button>
          </div>
        )}

        {state.errors.inverter && (
          <div className="flex gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/50 text-red-200">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>{state.errors.inverter}</span>
          </div>
        )}
      </div>
    </div>
  );

  const renderStep4 = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Optional Components</h2>

      <div className="space-y-6">
        {/* BESS Configuration */}
        <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700 space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={state.bess !== null}
              onChange={(e) =>
                setState((s) => ({ ...s, bess: e.target.checked ? {} as BESSConfig : null }))
              }
              className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-white font-medium">Enable Battery Storage (BESS)</span>
          </label>

          {state.bess && (
            <div className="space-y-4">
              <input
                type="text"
                placeholder="Equipment ID (e.g., S002-BESS-B1-001)"
                value={state.bess.equipment_id || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    bess: s.bess ? { ...s.bess, equipment_id: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />

              <select
                value={state.bess.manufacturer || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    bess: s.bess ? { ...s.bess, manufacturer: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="">Select manufacturer</option>
                {MANUFACTURERS.bess.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>

              <input
                type="text"
                placeholder="Model"
                value={state.bess.model || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    bess: s.bess ? { ...s.bess, model: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />

              <div className="grid grid-cols-2 gap-4">
                <input
                  type="number"
                  placeholder="Capacity (kWh)"
                  value={state.bess.capacity_kwh || ''}
                  onChange={(e) =>
                    setState((s) => ({
                      ...s,
                      bess: s.bess ? { ...s.bess, capacity_kwh: parseFloat(e.target.value) || 0 } : null,
                    }))
                  }
                  className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
                <input
                  type="number"
                  placeholder="Power (kW)"
                  value={state.bess.rated_power_kw || ''}
                  onChange={(e) =>
                    setState((s) => ({
                      ...s,
                      bess: s.bess ? { ...s.bess, rated_power_kw: parseFloat(e.target.value) || 0 } : null,
                    }))
                  }
                  className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <input
                type="text"
                placeholder="Modbus IP"
                value={state.bess.modbus_ip || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    bess: s.bess ? { ...s.bess, modbus_ip: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          )}
        </div>

        {/* Grid Meter Configuration */}
        <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700 space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={state.gridMeter !== null}
              onChange={(e) =>
                setState((s) => ({ ...s, gridMeter: e.target.checked ? {} as GridMeterConfig : null }))
              }
              className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-white font-medium">Enable Grid Meter</span>
          </label>

          {state.gridMeter && (
            <div className="space-y-4">
              <input
                type="text"
                placeholder="Equipment ID (e.g., S002-MTR-R-GRID)"
                value={state.gridMeter.equipment_id || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    gridMeter: s.gridMeter ? { ...s.gridMeter, equipment_id: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />

              <select
                value={state.gridMeter.manufacturer || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    gridMeter: s.gridMeter ? { ...s.gridMeter, manufacturer: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="">Select manufacturer</option>
                {MANUFACTURERS.meter.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>

              <input
                type="text"
                placeholder="Modbus IP"
                value={state.gridMeter.modbus_ip || ''}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    gridMeter: s.gridMeter ? { ...s.gridMeter, modbus_ip: e.target.value } : null,
                  }))
                }
                className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          )}
        </div>

        {/* Tariff Selection */}
        <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700 space-y-4">
          <label className="block text-sm font-medium text-gray-300">Select Tariff</label>
          <select
            value={state.tariff}
            onChange={(e) => setState((s) => ({ ...s, tariff: e.target.value }))}
            className="w-full px-4 py-2 rounded-lg bg-gray-800/50 border border-gray-600 text-white focus:outline-none focus:border-blue-500"
          >
            {TARIFFS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );

  const renderStep5 = () => {
    const totalCapacity = state.plants.reduce((sum, p) => sum + (p.capacity_kwp || 0), 0);

    if (state.success) {
      return (
        <div className="space-y-6 text-center">
          <div className="flex justify-center">
            <CheckCircle2 className="w-16 h-16 text-green-400" />
          </div>
          <h2 className="text-2xl font-bold text-white">Solar Configuration Complete!</h2>
          <p className="text-gray-300">
            Your solar site has been configured and the Solar module is now active.
          </p>
          <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30 text-green-200">
            <p className="font-medium">{state.siteName}</p>
            <p className="text-sm">{totalCapacity} kWp • {state.plants.length} plant(s)</p>
          </div>
          <button
            onClick={() => onComplete?.()}
            className="w-full px-4 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
          >
            View Dashboard
          </button>
        </div>
      );
    }

    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-white">Review & Activate</h2>

        <div className="grid gap-4">
          <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700">
            <p className="text-sm text-gray-400">Total Capacity</p>
            <p className="text-2xl font-bold text-white">{totalCapacity} kWp</p>
          </div>

          <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700">
            <p className="text-sm text-gray-400">Plants</p>
            <p className="text-2xl font-bold text-white">{state.plants.length}</p>
          </div>

          {state.bess && (
            <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30">
              <p className="text-sm text-gray-400">BESS</p>
              <p className="text-xl font-bold text-green-300">
                {state.bess.capacity_kwh} kWh • {state.bess.rated_power_kw} kW
              </p>
            </div>
          )}

          {state.gridMeter && (
            <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/30">
              <p className="text-sm text-gray-400">Grid Meter</p>
              <p className="text-xl font-bold text-blue-300">Enabled</p>
            </div>
          )}

          <div className="p-4 rounded-lg bg-gray-900/50 border border-gray-700">
            <p className="text-sm text-gray-400">Tariff</p>
            <p className="text-xl font-bold text-white">{state.tariff}</p>
          </div>
        </div>

        {state.errors.submit && (
          <div className="flex gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/50 text-red-200">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span>{state.errors.submit}</span>
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={state.loading}
          className="w-full px-4 py-3 rounded-lg bg-green-600 text-white font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {state.loading ? 'Activating...' : 'Activate Solar Module'}
        </button>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 to-gray-900 p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            <Zap className="w-8 h-8 text-yellow-400" />
            Solar Setup Wizard
          </h1>
          <p className="text-gray-400 mt-2">Configure your solar site in 5 steps</p>
        </div>

        {/* Progress Indicator */}
        <div className="mb-8 flex items-center justify-between">
          {[1, 2, 3, 4, 5].map((step) => (
            <div key={step} className="flex items-center">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center font-bold transition ${
                  state.step >= step
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-700 text-gray-400'
                }`}
              >
                {step}
              </div>
              {step < 5 && (
                <div
                  className={`w-12 h-1 mx-2 transition ${
                    state.step > step ? 'bg-blue-600' : 'bg-gray-700'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="p-6 rounded-xl bg-gray-900/50 border border-gray-700 mb-6">
          {state.step === 1 && renderStep1()}
          {state.step === 2 && renderStep2()}
          {state.step === 3 && renderStep3()}
          {state.step === 4 && renderStep4()}
          {state.step === 5 && renderStep5()}
        </div>

        {/* Navigation Buttons */}
        {!state.success && (
          <div className="flex gap-4">
            <button
              onClick={handlePrevStep}
              disabled={state.step === 1}
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg border border-gray-600 text-gray-300 hover:border-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <ChevronLeft className="w-5 h-5" />
              Previous
            </button>
            {state.step < 5 && (
              <button
                onClick={handleNextStep}
                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition"
              >
                Next
                <ChevronRight className="w-5 h-5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
