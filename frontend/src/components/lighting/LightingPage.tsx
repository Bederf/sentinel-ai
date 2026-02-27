/**
 * LightingPage Component - Lighting Control Page
 *
 * Shows zone-based lighting control with:
 * - Building selector dropdown
 * - Zone grid sourced from Supabase zones table
 * - Brightness, occupancy, daylight metrics per zone
 * - Manual brightness override sliders
 * - Zone status (active, standby, fault)
 * - Real-time occupancy and daylight data from simulation
 */

import { useState, useEffect, useMemo } from 'react';
import { Lightbulb, Sun, Users } from 'lucide-react';
import { useSimulation } from '@/contexts/SimulationContext';
import { BuildingSelector } from '../BuildingSelector';
import { api, isExpectedApiError } from '@/lib/api';
import { hvacApi } from '@/lib/hvacApi';
import type { Site } from '@/lib/api';
import type { HVACZone } from '@/lib/hvacApi';

interface LightingZone {
  id: string;
  code: string;
  name: string;
  floor: string;
  brightness: number;
  occupancy: number;
  daylight: number;
  status: 'active' | 'standby' | 'fault';
}

// Window factor per floor — higher floors get more daylight
const FLOOR_WINDOW_FACTOR: Record<string, number> = {
  L0: 0.55, L1: 0.65, L2: 0.75, L3: 0.85,
};

// Occupancy weight by zone letter (cardinal position)
const ZONE_OCC_WEIGHT: Record<string, number> = {
  A: 0.90, // North — high traffic
  B: 0.80, // East
  C: 1.00, // Central — core workspace
  D: 0.70, // West
  E: 0.60, // South — lower traffic
};

// Min brightness by floor
const FLOOR_MIN_BRIGHT: Record<string, number> = {
  L0: 35, L1: 30, L2: 25, L3: 25,
};

export function LightingPage() {
  const { running: isSimulationRunning, cloudCover, occupancyPercent, simulatedHour, daysSimulated } = useSimulation();

  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [rawZones, setRawZones] = useState<HVACZone[]>([]);

  // Fetch sites on mount and set default
  useEffect(() => {
    let mounted = true;
    async function loadSites() {
      try {
        const sitesData = await api.getSites();
        if (!mounted) return;
        setSites(sitesData);
        const defaultSite = sitesData.find(s => s.name?.includes('Sandton')) || sitesData[0];
        if (defaultSite) {
          setSelectedSiteId(defaultSite.id);
        }
      } catch (err) {
        if (!isExpectedApiError(err)) {
          console.error("Failed to fetch sites:", err);
        }
      }
    }
    loadSites();
    return () => { mounted = false; };
  }, []);

  // Fetch zones from Supabase when site changes
  useEffect(() => {
    if (!selectedSiteId) return;
    let mounted = true;
    async function loadZones() {
      try {
        const data = await hvacApi.getZones(selectedSiteId);
        if (!mounted) return;
        setRawZones(data.zones || []);
      } catch (err) {
        if (!isExpectedApiError(err)) {
          console.error("Failed to fetch zones:", err);
        }
      }
    }
    loadZones();
    return () => { mounted = false; };
  }, [selectedSiteId]);

  // Compute lighting zones reactively from simulation state + Supabase zones
  const zones: LightingZone[] = useMemo(() => {
    if (rawZones.length === 0) return [];

    const hour = simulatedHour || 0;
    const cloud = cloudCover || 0;
    const globalOcc = occupancyPercent || 0;

    // Solar daylight curve: peak at noon, 0 at night
    let solarFactor = 0;
    if (hour >= 6 && hour <= 18) {
      solarFactor = Math.max(0, Math.cos((hour - 12) * Math.PI / 12));
    }
    const cloudMult = 1 - (cloud / 100) * 0.6;

    return rawZones.map((z) => {
      const floor = z.floor || 'L0';
      // Extract zone letter from zone_name (e.g. "L0 North" → derive from zone_id pattern)
      const zoneLetter = z.zone_id?.replace(/^Zone-/, '').slice(-1) || '';
      // Map zone_id last digit to letter: 1→A, 2→B, 3→C, 4→D, 5→E
      const digitToLetter: Record<string, string> = { '1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E' };
      const letter = digitToLetter[zoneLetter] || 'C';

      const windowFactor = FLOOR_WINDOW_FACTOR[floor] ?? 0.60;
      const occWeight = ZONE_OCC_WEIGHT[letter] ?? 0.80;
      const minBright = FLOOR_MIN_BRIGHT[floor] ?? 30;

      // Per-zone daylight: window exposure × solar × cloud
      const daylight = isSimulationRunning
        ? Math.round(windowFactor * solarFactor * cloudMult * 100)
        : Math.round(windowFactor * 60);

      // Per-zone occupancy: global occupancy scaled by zone weight
      const zoneOcc = isSimulationRunning
        ? Math.round(Math.min(100, Math.max(0, globalOcc * occWeight)))
        : Math.round(50 * occWeight);

      // Brightness: daylight harvesting logic
      const targetBright = zoneOcc > 10 ? 85 : 30;
      const daylightOffset = daylight * 0.7;
      const brightness = isSimulationRunning
        ? Math.round(Math.max(minBright, Math.min(100, targetBright - daylightOffset + (zoneOcc > 10 ? 10 : 0))))
        : 75;

      const status: LightingZone['status'] = zoneOcc < 15 ? 'standby' : 'active';

      return {
        id: z.zone_id,
        code: z.zone_id,
        name: z.zone_name || z.zone_id,
        floor,
        brightness,
        occupancy: zoneOcc,
        daylight,
        status,
      };
    });
  }, [isSimulationRunning, simulatedHour, cloudCover, occupancyPercent, rawZones]);

  // Group zones by floor for display
  const floors = useMemo(() => {
    const map = new Map<string, LightingZone[]>();
    for (const z of zones) {
      const existing = map.get(z.floor) || [];
      existing.push(z);
      map.set(z.floor, existing);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [zones]);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(250, 204, 21, 0.15)" }}>
              <Lightbulb className="h-6 w-6" style={{ color: "#FACC15" }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  Lighting Control
                </h1>
                {isSimulationRunning && (
                  <div className="px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      background: 'rgba(250, 204, 21, 0.15)',
                      color: '#FACC15',
                    }}
                  >
                    Live &bull; {cloudCover?.toFixed(0)}% cloud
                  </div>
                )}
              </div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {isSimulationRunning
                  ? `Real-time daylight harvesting \u2022 Hour ${simulatedHour}:00 (Day ${daysSimulated}/365)`
                  : 'Intelligent Lighting Management'
                }
              </p>
            </div>
          </div>
          <BuildingSelector
            sites={sites}
            value={selectedSiteId}
            onChange={setSelectedSiteId}
          />
        </div>
      </div>

      {/* Zone Grid grouped by floor */}
      {zones.length === 0 ? (
        <div className="text-center py-12" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          No lighting zones found for this site
        </div>
      ) : (
        floors.map(([floor, floorZones]) => (
          <div key={floor} className="mb-6">
            <h2 className="text-sm font-semibold mb-3 uppercase tracking-wide"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {floor}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {floorZones.map((zone) => (
                <LightingZoneCard key={zone.id} zone={zone} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// Lighting Zone Card Component
function LightingZoneCard({ zone }: { zone: LightingZone }) {
  const [brightness, setBrightness] = useState(zone.brightness);

  // Sync when simulation updates zone brightness
  useEffect(() => {
    setBrightness(zone.brightness);
  }, [zone.brightness]);

  const handleBrightnessChange = async (newBrightness: number) => {
    setBrightness(newBrightness);
  };

  const statusColors = {
    active: { bg: "rgba(34, 197, 94, 0.15)", text: "#22C55E" },
    standby: { bg: "rgba(251, 191, 36, 0.15)", text: "#FBB924" },
    fault: { bg: "rgba(239, 68, 68, 0.15)", text: "#EF4444" }
  };

  const statusColor = statusColors[zone.status];

  return (
    <div
      className="rounded-md p-4"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)"
      }}
    >
      {/* Zone Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {zone.name}
          </h3>
          <span className="text-xs font-mono" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {zone.code}
          </span>
        </div>
        <span
          className="text-xs px-2 py-1 rounded capitalize"
          style={{ background: statusColor.bg, color: statusColor.text }}
        >
          {zone.status}
        </span>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <ZoneMetric
          icon={<Lightbulb className="w-4 h-4" style={{ color: "#FACC15" }} />}
          label="Brightness"
          value={`${brightness}%`}
        />
        <ZoneMetric
          icon={<Users className="w-4 h-4" style={{ color: "#3B82F6" }} />}
          label="Occupancy"
          value={`${zone.occupancy}%`}
        />
        <ZoneMetric
          icon={<Sun className="w-4 h-4" style={{ color: "#F59E0B" }} />}
          label="Daylight"
          value={`${zone.daylight}%`}
        />
      </div>

      {/* Brightness Slider */}
      <div className="space-y-2">
        <label className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Manual Override
        </label>
        <input
          type="range"
          min="0"
          max="100"
          value={brightness}
          onChange={(e) => handleBrightnessChange(Number(e.target.value))}
          className="w-full h-2 rounded-lg appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, #FACC15 0%, #FACC15 ${brightness}%, #374151 ${brightness}%, #374151 100%)`
          }}
        />
        <div className="flex justify-between text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          <span>0%</span>
          <span className="font-medium" style={{ color: "#FACC15" }}>{brightness}%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}

function ZoneMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div>
      <div className="flex items-center gap-1 mb-1">
        {icon}
        <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {label}
        </span>
      </div>
      <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
        {value}
      </p>
    </div>
  );
}
