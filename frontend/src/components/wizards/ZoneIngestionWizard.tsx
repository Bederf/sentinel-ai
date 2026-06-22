/**
 * Zone Ingestion Wizard
 *
 * Multi-step wizard for building zone and desk configuration during onboarding.
 *
 * Steps:
 * 1. Floor Plan Upload (optional reference)
 * 2. Zone Definition (zone_id, floor, type, area)
 * 3. Desk Entry (manual, grid-based, or CSV import)
 * 4. 3D Preview (visual verification)
 * 5. Submit (save configuration)
 */

import { useState, useCallback, useMemo } from 'react';
import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, Loader2, Plus, Trash2, Upload, FileCheck, Wand2 } from 'lucide-react';
import type { ZoneConfig, DeskConfig, BuildingConfigResponse } from '@/lib/api/zone_ingestion';
import { zoneIngestionApi, floorPlanApi } from '@/lib/api/zone_ingestion';

interface ZoneIngestionWizardProps {
  siteId: string;
  siteName?: string;
  onComplete?: (zones: ZoneConfig[], desks: DeskConfig[]) => void;
  onSkip?: () => void;
  onCancel?: () => void;
}

const ZONE_TYPES = [
  'open_office',
  'meeting_room',
  'plant_room',
  'storage',
  'stairwell',
  'corridor',
  'lobby',
  'restroom',
  'cafeteria',
  'server_room',
  'comms_room',
  'mechanical',
  'electrical',
  'ward',
  'theatre',
  'icu',
  'consulting_room',
  'retail',
  'food_court',
  'back_of_house',
  'public_area',
];

const FLOOR_CODE_PATTERN = /^(B[1-9]\d*|G|L\d+|R)$/;
const DEFAULT_FLOORS = ['B1', 'B2', 'G', 'L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9', 'R'];

interface IngestionWizardState {
  step: 1 | 2 | 3 | 4 | 5;
  zones: ZoneConfig[];
  desks: DeskConfig[];
  draftZone: Partial<ZoneConfig>;
  draftDesk: Partial<DeskConfig>;
  errors: Record<string, string>;
  loading: boolean;
  success: boolean;
  extractedConfig: BuildingConfigResponse | null;
  uploadingFloorPlan: boolean;
  autoPlanLoading: boolean;
  autoPlanMessage: string | null;
}

export function ZoneIngestionWizard({
  siteId,
  siteName,
  onComplete,
  onCancel,
}: ZoneIngestionWizardProps) {
  const [state, setState] = useState<IngestionWizardState>({
    step: 1,
    zones: [],
    desks: [],
    draftZone: {},
    draftDesk: {},
    errors: {},
    loading: false,
    success: false,
    extractedConfig: null,
    uploadingFloorPlan: false,
    autoPlanLoading: false,
    autoPlanMessage: null,
  });

  // Validate zone data
  const validateZone = useCallback((zone: Partial<ZoneConfig>): string | null => {
    if (!zone.zone_id?.trim()) return 'Zone ID is required';
    if (!zone.zone_name?.trim()) return 'Zone name is required';
    if (!zone.floor) return 'Floor is required';
    if (!FLOOR_CODE_PATTERN.test(zone.floor)) return 'Floor must be G, R, L# or B#';
    if (!zone.zone_type) return 'Zone type is required';

    // Check for duplicates
    if (state.zones.some((z) => z.zone_id === zone.zone_id)) {
      return 'Zone ID already exists';
    }

    return null;
  }, [state.zones]);

  // Validate desk data
  const validateDesk = useCallback((desk: Partial<DeskConfig>): string | null => {
    if (!desk.desk_id?.trim()) return 'Desk ID is required';
    if (!desk.zone_id) return 'Zone is required';
    if (!desk.coordinates) return 'Coordinates are required';
    if (typeof desk.coordinates.x !== 'number' || typeof desk.coordinates.z !== 'number') {
      return 'Coordinates must be numbers';
    }
    if (desk.coordinates.x < 0 || desk.coordinates.x > 50 || desk.coordinates.z < 0 || desk.coordinates.z > 50) {
      return 'Coordinates out of bounds (0-50)';
    }

    // Check for duplicates
    if (state.desks.some((d) => d.desk_id === desk.desk_id)) {
      return 'Desk ID already exists';
    }

    return null;
  }, [state.desks]);

  const handleFloorPlanUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setState((s) => ({ ...s, uploadingFloorPlan: true, errors: {} }));

    try {
      let config: BuildingConfigResponse;
      if (file.name.toLowerCase().endsWith('.pdf')) {
        config = await floorPlanApi.extractFromPdf(file, siteId, siteName, 3);
      } else if (file.name.toLowerCase().endsWith('.dxf')) {
        config = await floorPlanApi.extractFromDxf(file, siteId, siteName);
      } else {
        setState((s) => ({ ...s, errors: { floorPlan: 'Unsupported file type. Use PDF or DXF.' }, uploadingFloorPlan: false }));
        return;
      }

      setState((s) => ({
        ...s,
        extractedConfig: config,
        uploadingFloorPlan: false,
        errors: {},
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Extraction failed';
      setState((s) => ({ ...s, errors: { floorPlan: message }, uploadingFloorPlan: false }));
    }
  }, [siteId, siteName]);

  const applyExtractedConfig = useCallback(() => {
    if (!state.extractedConfig) return;

    const extractedZones: ZoneConfig[] = state.extractedConfig.zones.map((z) => ({
      zone_id: z.zone_id,
      zone_name: z.zone_id.replace('Zone-', 'Zone ').replace('-', ' '),
      floor: z.floor,
      zone_type: z.zone_type || 'open_office',
    }));

    const extractedDesks: DeskConfig[] = state.extractedConfig.equipment
      .filter((e) => e.equipment_type === 'fcu' || e.equipment_type === 'vav')
      .map((e, idx) => ({
        desk_id: `${idx + 1}`,
        zone_id: `Zone-${e.floor}-${e.zone || 'A'}`,
        floor: e.floor,
        context: 'open_plan' as const,
        coordinates: { x: e.x, y: 0, z: e.y },
      }));

    setState((s) => ({
      ...s,
      zones: extractedZones,
      desks: extractedDesks,
      step: 2,
      extractedConfig: null,
    }));
  }, [state.extractedConfig]);

  const generateAutoPlan = useCallback(async () => {
    setState((s) => ({ ...s, autoPlanLoading: true, autoPlanMessage: null, errors: {} }));
    try {
      const plan = await zoneIngestionApi.generateAutoPlan(siteId);
      setState((s) => ({
        ...s,
        zones: plan.zones,
        desks: plan.desks,
        autoPlanLoading: false,
        autoPlanMessage: `${plan.strategy.replace(/_/g, ' ')} generated ${plan.zones.length} zones and ${plan.desks.length} desks. Review before submit.`,
        step: 2,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Auto zone generation failed';
      setState((s) => ({ ...s, autoPlanLoading: false, errors: { autoPlan: message } }));
    }
  }, [siteId]);

  const addZone = () => {
    const error = validateZone(state.draftZone);
    if (error) {
      setState((s) => ({ ...s, errors: { zone: error } }));
      return;
    }

    setState((s) => ({
      ...s,
      zones: [...s.zones, state.draftZone as ZoneConfig],
      draftZone: {},
      errors: {},
    }));
  };

  const removeZone = (zoneId: string) => {
    setState((s) => ({
      ...s,
      zones: s.zones.filter((z) => z.zone_id !== zoneId),
      desks: s.desks.filter((d) => d.zone_id !== zoneId),
    }));
  };

  const addDesk = () => {
    const error = validateDesk(state.draftDesk);
    if (error) {
      setState((s) => ({ ...s, errors: { desk: error } }));
      return;
    }

    setState((s) => ({
      ...s,
      desks: [...s.desks, state.draftDesk as DeskConfig],
      draftDesk: {},
      errors: {},
    }));
  };

  const removeDesk = (deskId: string) => {
    setState((s) => ({
      ...s,
      desks: s.desks.filter((d) => d.desk_id !== deskId),
    }));
  };

  const generateGridDesks = (zoneId: string, rows: number, cols: number) => {
    const zone = state.zones.find((z) => z.zone_id === zoneId);
    if (!zone) return;

    const zoneIndex = state.zones.indexOf(zone);
    const zoneOffsetX = zoneIndex * 6;

    const newDesks: DeskConfig[] = [];
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const deskIndex = state.desks.length + newDesks.length + 1;
        newDesks.push({
          desk_id: `${deskIndex}`,
          zone_id: zoneId,
          floor: zone.floor,
          context: 'open_plan',
          coordinates: {
            x: zoneOffsetX + col * 1.2 + 0.6,
            y: zone.floor === 'L0' ? 3.5 : zone.floor === 'L1' ? 6.5 : zone.floor === 'L2' ? 9.5 : 3.5,
            z: row * 5 + 2.5,
          },
        });
      }
    }

    setState((s) => ({
      ...s,
      desks: [...s.desks, ...newDesks],
    }));
  };

  const handleSubmit = async () => {
    if (state.zones.length === 0) {
      setState((s) => ({ ...s, errors: { zones: 'At least one zone is required' } }));
      return;
    }

    setState((s) => ({ ...s, loading: true, errors: {} }));

    try {
      // Submit zones
      const zonesResponse = await zoneIngestionApi.ingestZones(siteId, { zones: state.zones });
      if (zonesResponse.status !== 'success') {
        throw new Error(zonesResponse.message || 'Failed to ingest zones');
      }

      // Submit desks (if any)
      if (state.desks.length > 0) {
        const desksResponse = await zoneIngestionApi.ingestDesks(siteId, { desks: state.desks });
        if (desksResponse.status !== 'success') {
          throw new Error(desksResponse.message || 'Failed to ingest desks');
        }
      }

      setState((s) => ({ ...s, success: true, loading: false }));
      onComplete?.(state.zones, state.desks);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error occurred';
      setState((s) => ({ ...s, errors: { submit: message }, loading: false }));
    }
  };

  const nextStep = () => {
    if (state.step < 5) {
      setState((s) => ({ ...s, step: (s.step + 1) as any }));
    }
  };

  const prevStep = () => {
    if (state.step > 1) {
      setState((s) => ({ ...s, step: (s.step - 1) as any }));
    }
  };

  const zoneStats = useMemo(() => {
    const desksPerZone: Record<string, number> = {};
    state.desks.forEach((d) => {
      desksPerZone[d.zone_id] = (desksPerZone[d.zone_id] || 0) + 1;
    });
    return desksPerZone;
  }, [state.desks]);

  if (state.success) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
        <div className="bg-white rounded-lg shadow-lg max-w-md p-8 text-center">
          <CheckCircle2 className="w-16 h-16 text-green-600 mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-2">Configuration Complete!</h2>
          <p className="text-gray-600 mb-2">
            Successfully configured {state.zones.length} zones with {state.desks.length} desks.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-gradient-to-r from-blue-600 to-blue-700 text-white p-6 border-b">
          <h1 className="text-2xl font-bold mb-1">Zone Configuration Wizard</h1>
          <p className="text-blue-100">{siteName} • Step {state.step} of 5</p>
          <div className="mt-4 flex gap-1 h-1">
            {[1, 2, 3, 4, 5].map((step) => (
              <div
                key={step}
                className={`flex-1 rounded-full transition ${
                  step <= state.step ? 'bg-white' : 'bg-blue-400'
                }`}
              />
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Floor Plan Upload */}
          {state.step === 1 && (
            <div>
              <h2 className="text-xl font-bold mb-4">Step 1: Floor Plan (Optional)</h2>

              {!state.extractedConfig ? (
                <div className="space-y-4">
                  <div className="border border-blue-200 bg-blue-50 rounded-lg p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-semibold text-blue-950">Generate from site settings</p>
                        <p className="text-sm text-blue-800 mt-1">
                          Uses building type, floors, desks, and area to create an editable zone draft.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={generateAutoPlan}
                        disabled={state.autoPlanLoading}
                        className="inline-flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50"
                      >
                        {state.autoPlanLoading ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Wand2 className="w-4 h-4" />
                        )}
                        Auto Generate
                      </button>
                    </div>
                    {state.autoPlanMessage && (
                      <p className="text-sm text-blue-800 mt-3">{state.autoPlanMessage}</p>
                    )}
                    {state.errors.autoPlan && (
                      <p className="text-red-600 mt-2 text-sm">{state.errors.autoPlan}</p>
                    )}
                  </div>

                  <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                    <p className="text-gray-600 mb-4">Upload a floor plan to auto-populate zones and equipment</p>
                    <input
                      type="file"
                      accept=".pdf,.dxf,image/*"
                      className="hidden"
                      id="floor-plan-input"
                      onChange={handleFloorPlanUpload}
                    />
                    <label
                      htmlFor="floor-plan-input"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg cursor-pointer hover:bg-blue-700 transition disabled:opacity-50"
                    >
                      {state.uploadingFloorPlan ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Extracting...
                        </>
                      ) : (
                        <>
                          <Upload className="w-4 h-4" />
                          Choose File
                        </>
                      )}
                    </label>
                    <p className="text-sm text-gray-500 mt-4">PDF or DXF floor plan · Click Next to skip</p>
                    {state.errors.floorPlan && (
                      <p className="text-red-600 mt-2 text-sm">{state.errors.floorPlan}</p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-start gap-3">
                    <FileCheck className="w-5 h-5 text-green-600 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium text-green-900">Floor plan extracted</p>
                      <p className="text-sm text-green-700 mt-1">
                        {state.extractedConfig.zones.length} zones, {state.extractedConfig.equipment.length} equipment found
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={applyExtractedConfig}
                      className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition"
                    >
                      Apply to Zone Configuration
                    </button>
                    <button
                      onClick={() => setState((s) => ({ ...s, extractedConfig: null }))}
                      className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition"
                    >
                      Clear
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 2: Zone Definition */}
          {state.step === 2 && (
            <div>
              <h2 className="text-xl font-bold mb-4">Step 2: Define Zones</h2>

              {state.autoPlanMessage && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-sm text-blue-800">
                  {state.autoPlanMessage}
                </div>
              )}

              {/* Zone Form */}
              <div className="bg-gray-50 p-4 rounded-lg mb-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    placeholder="Zone ID (e.g., Zone-L1-A)"
                    value={state.draftZone.zone_id || ''}
                    onChange={(e) =>
                      setState((s) => ({
                        ...s,
                        draftZone: { ...s.draftZone, zone_id: e.target.value },
                      }))
                    }
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    type="text"
                    placeholder="Zone Name"
                    value={state.draftZone.zone_name || ''}
                    onChange={(e) =>
                      setState((s) => ({
                        ...s,
                        draftZone: { ...s.draftZone, zone_name: e.target.value },
                      }))
                    }
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <select
                    value={state.draftZone.floor || ''}
                    onChange={(e) =>
                      setState((s) => ({
                        ...s,
                        draftZone: { ...s.draftZone, floor: e.target.value },
                      }))
                    }
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select Floor</option>
                    {DEFAULT_FLOORS.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>

                  <select
                    value={state.draftZone.zone_type || ''}
                    onChange={(e) =>
                      setState((s) => ({
                        ...s,
                        draftZone: { ...s.draftZone, zone_type: e.target.value },
                      }))
                    }
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select Type</option>
                    {ZONE_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                </div>

                {state.errors.zone && (
                  <div className="flex items-center gap-2 text-red-600 text-sm">
                    <AlertCircle className="w-4 h-4" />
                    {state.errors.zone}
                  </div>
                )}

                <button
                  onClick={addZone}
                  className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition flex items-center justify-center gap-2"
                >
                  <Plus className="w-4 h-4" /> Add Zone
                </button>
              </div>

              {/* Zones List */}
              <div className="space-y-2">
                {state.zones.map((zone) => (
                  <div key={zone.zone_id} className="flex items-center justify-between p-3 bg-gray-100 rounded-lg">
                    <div>
                      <p className="font-semibold">{zone.zone_id}</p>
                      <p className="text-sm text-gray-600">
                        {zone.floor} • {zone.zone_type.replace(/_/g, ' ')}
                      </p>
                    </div>
                    <button
                      onClick={() => removeZone(zone.zone_id)}
                      className="text-red-600 hover:text-red-700"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>

              {state.zones.length === 0 && (
                <p className="text-center text-gray-500 py-4">No zones added yet</p>
              )}
            </div>
          )}

          {/* Step 3: Desk Entry */}
          {state.step === 3 && (
            <div>
              <h2 className="text-xl font-bold mb-4">Step 3: Define Desks</h2>

              {state.zones.length === 0 ? (
                <div className="bg-yellow-50 p-4 rounded-lg text-yellow-800 flex items-center gap-2">
                  <AlertCircle className="w-5 h-5" />
                  <p>Please add zones first (go to previous step)</p>
                </div>
              ) : (
                <>
                  {/* Desk Form */}
                  <div className="bg-gray-50 p-4 rounded-lg mb-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <input
                        type="text"
                        placeholder="Desk ID"
                        value={state.draftDesk.desk_id || ''}
                        onChange={(e) =>
                          setState((s) => ({
                            ...s,
                            draftDesk: { ...s.draftDesk, desk_id: e.target.value },
                          }))
                        }
                        className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />

                      <select
                        value={state.draftDesk.zone_id || ''}
                        onChange={(e) =>
                          setState((s) => ({
                            ...s,
                            draftDesk: { ...s.draftDesk, zone_id: e.target.value },
                          }))
                        }
                        className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="">Select Zone</option>
                        {state.zones.map((z) => (
                          <option key={z.zone_id} value={z.zone_id}>
                            {z.zone_id}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                      <input
                        type="number"
                        placeholder="X (0-50)"
                        step="0.1"
                        min="0"
                        max="50"
                        value={state.draftDesk.coordinates?.x || ''}
                        onChange={(e) =>
                          setState((s) => ({
                            ...s,
                            draftDesk: {
                              ...s.draftDesk,
                              coordinates: {
                                ...(s.draftDesk.coordinates || { y: 3.5, z: 0 }),
                                x: parseFloat(e.target.value) || 0,
                              },
                            },
                          }))
                        }
                        className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <input
                        type="number"
                        placeholder="Y (auto)"
                        disabled
                        className="px-3 py-2 border rounded-lg bg-gray-200"
                      />
                      <input
                        type="number"
                        placeholder="Z (0-50)"
                        step="0.1"
                        min="0"
                        max="50"
                        value={state.draftDesk.coordinates?.z || ''}
                        onChange={(e) =>
                          setState((s) => ({
                            ...s,
                            draftDesk: {
                              ...s.draftDesk,
                              coordinates: {
                                ...(s.draftDesk.coordinates || { x: 0, y: 3.5 }),
                                z: parseFloat(e.target.value) || 0,
                              },
                            },
                          }))
                        }
                        className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>

                    {state.errors.desk && (
                      <div className="flex items-center gap-2 text-red-600 text-sm">
                        <AlertCircle className="w-4 h-4" />
                        {state.errors.desk}
                      </div>
                    )}

                    <button
                      onClick={addDesk}
                      className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition flex items-center justify-center gap-2"
                    >
                      <Plus className="w-4 h-4" /> Add Desk
                    </button>
                  </div>

                  {/* Grid Generator */}
                  <div className="bg-blue-50 p-3 rounded-lg mb-4">
                    <p className="text-sm font-semibold mb-2">Quick Add: Generate Grid</p>
                    {state.zones.map((zone) => (
                      <div key={zone.zone_id} className="flex gap-2 mb-2">
                        <button
                          onClick={() => generateGridDesks(zone.zone_id, 4, 5)}
                          className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
                        >
                          {zone.zone_id} (4×5)
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Desks List */}
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {state.desks.map((desk) => (
                      <div key={desk.desk_id} className="flex items-center justify-between p-2 bg-gray-100 rounded text-sm">
                        <div>
                          <p className="font-semibold">{desk.desk_id}</p>
                          <p className="text-gray-600">
                            {desk.zone_id} • ({desk.coordinates.x.toFixed(1)}, {desk.coordinates.z.toFixed(1)})
                          </p>
                        </div>
                        <button
                          onClick={() => removeDesk(desk.desk_id)}
                          className="text-red-600 hover:text-red-700"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>

                  <div className="mt-3 text-sm text-gray-600">
                    {Object.entries(zoneStats).map(([zoneId, count]) => (
                      <p key={zoneId}>
                        {zoneId}: {count} desks
                      </p>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Step 4: Preview */}
          {state.step === 4 && (
            <div>
              <h2 className="text-xl font-bold mb-4">Step 4: Review Configuration</h2>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h3 className="font-semibold mb-2">Zones ({state.zones.length})</h3>
                  <div className="space-y-1 text-sm max-h-48 overflow-y-auto">
                    {state.zones.map((z) => (
                      <p key={z.zone_id} className="text-gray-700">
                        {z.zone_id} ({z.floor})
                      </p>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold mb-2">Desks ({state.desks.length})</h3>
                  <div className="space-y-1 text-sm">
                    {Object.entries(zoneStats).map(([zoneId, count]) => (
                      <p key={zoneId} className="text-gray-700">
                        {zoneId}: {count} desks
                      </p>
                    ))}
                  </div>
                </div>
              </div>

              {state.errors.zones && (
                <div className="mt-4 flex items-center gap-2 text-red-600">
                  <AlertCircle className="w-5 h-5" />
                  {state.errors.zones}
                </div>
              )}
            </div>
          )}

          {/* Step 5: Submit */}
          {state.step === 5 && (
            <div>
              <h2 className="text-xl font-bold mb-4">Step 5: Confirm & Submit</h2>

              <div className="bg-green-50 p-4 rounded-lg border border-green-200 mb-4">
                <p className="text-green-800">
                  Ready to save configuration for <strong>{siteName}</strong>
                </p>
              </div>

              <div className="space-y-3 text-sm">
                <div>
                  <p className="font-semibold">Zones: {state.zones.length}</p>
                  <p className="text-gray-600">Will create building-level zone configuration</p>
                </div>
                <div>
                  <p className="font-semibold">Desks: {state.desks.length}</p>
                  <p className="text-gray-600">Will store workspace positions for 3D visualization</p>
                </div>
              </div>

              {state.errors.submit && (
                <div className="mt-4 flex items-center gap-2 text-red-600">
                  <AlertCircle className="w-5 h-5" />
                  {state.errors.submit}
                </div>
              )}

              {state.loading && (
                <div className="mt-4 flex items-center justify-center gap-2">
                  <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full" />
                  <span>Submitting...</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-gray-100 p-6 border-t flex justify-between">
          <button
            onClick={onCancel || (() => {})}
            className="px-4 py-2 text-gray-700 hover:text-gray-900 font-medium"
          >
            Cancel
          </button>

          <div className="flex gap-2">
            {state.step > 1 && (
              <button
                onClick={prevStep}
                className="px-4 py-2 bg-gray-300 text-gray-800 rounded-lg font-medium hover:bg-gray-400 transition flex items-center gap-2"
              >
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
            )}

            {state.step < 5 ? (
              <button
                onClick={nextStep}
                disabled={state.step === 2 && state.zones.length === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center gap-2"
              >
                Next <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={state.loading || state.zones.length === 0}
                className="px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition disabled:opacity-50 flex items-center gap-2"
              >
                <CheckCircle2 className="w-4 h-4" /> Submit
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
