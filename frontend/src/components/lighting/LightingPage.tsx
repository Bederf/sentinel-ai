/**
 * LightingPage Component - DALI Lighting Control Page
 *
 * Shows Tridonic DALI zone lighting with:
 * - Building selector dropdown
 * - Zone grid with brightness, occupancy, daylight metrics
 * - Manual brightness override sliders
 * - Zone status (active, standby, fault)
 * - Real-time occupancy and daylight data
 *
 * Used as dedicated page accessible via sidebar navigation.
 */

import { useState, useEffect, useMemo } from 'react';
import { Lightbulb, Sun, Users } from 'lucide-react';
import { useSimulation } from '@/contexts/SimulationContext';
import { BuildingSelector } from '../BuildingSelector';
import { api, isExpectedApiError } from '@/lib/api';
import type { Site } from '@/lib/api';

interface Zone {
  id: string;
  code: string;
  name: string;
  brightness: number;
  occupancy: number;
  daylight: number;
  status: 'active' | 'standby' | 'fault';
}

// Sites with DALI-2 lighting integration installed
const DALI_ENABLED_SITES = ["site-002"]; // Sandton City

export function LightingPage() {
  // Get simulation context for live daylight factor
  const { running: isSimulationRunning, cloudCover, occupancyPercent, simulatedHour, daysSimulated } = useSimulation();

  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");

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

  // Zone definitions with per-zone occupancy weights and window factors
  const ZONE_DEFS = useMemo(() => [
    { id: 'zone-001', code: 'S002-DALI-001', name: 'Level 0 - Reception',       windowFactor: 0.85, occWeight: 0.70, minBright: 40 },
    { id: 'zone-002', code: 'S002-DALI-002', name: 'Level 0 - Meeting Room A',  windowFactor: 0.70, occWeight: 1.20, minBright: 30 },
    { id: 'zone-003', code: 'S002-DALI-003', name: 'Level 1 - Open Plan',       windowFactor: 0.65, occWeight: 1.00, minBright: 25 },
    { id: 'zone-004', code: 'S002-DALI-101', name: 'Level 1 - Office Block',    windowFactor: 0.60, occWeight: 1.10, minBright: 30 },
    { id: 'zone-005', code: 'S002-DALI-102', name: 'Level 1 - Conference',      windowFactor: 0.55, occWeight: 1.30, minBright: 20 },
    { id: 'zone-006', code: 'S002-DALI-201', name: 'Level 2 - Admin',           windowFactor: 0.45, occWeight: 0.60, minBright: 25 },
    { id: 'zone-007', code: 'S002-DALI-202', name: 'Level 2 - IT Room',         windowFactor: 0.15, occWeight: 0.25, minBright: 60 },
    { id: 'zone-008', code: 'S002-DALI-203', name: 'Level 2 - Archive',         windowFactor: 0.08, occWeight: 0.10, minBright: 15 },
  ], []);

  // Compute zones reactively from simulation state
  const zones: Zone[] = useMemo(() => {
    const hour = simulatedHour || 0;
    const cloud = cloudCover || 0;
    const globalOcc = occupancyPercent || 0;

    // Solar daylight curve: peak at noon, 0 at night
    let solarFactor = 0;
    if (hour >= 6 && hour <= 18) {
      solarFactor = Math.max(0, Math.cos((hour - 12) * Math.PI / 12));
    }
    // Cloud reduces daylight
    const cloudMult = 1 - (cloud / 100) * 0.6;

    return ZONE_DEFS.map((def) => {
      // Per-zone daylight: window exposure × solar × cloud
      const daylight = isSimulationRunning
        ? Math.round(def.windowFactor * solarFactor * cloudMult * 100)
        : Math.round(def.windowFactor * 60);

      // Per-zone occupancy: global occupancy scaled by zone weight, clamped 0-100
      const zoneOcc = isSimulationRunning
        ? Math.round(Math.min(100, Math.max(0, globalOcc * def.occWeight)))
        : Math.round(50 * def.occWeight);

      // DALI brightness: Tridonic daylight harvesting logic
      // High daylight → reduce artificial light; high occupancy → ensure minimum
      // Target lux maintained: brightness = max(minBright, target - daylight contribution)
      const targetBright = zoneOcc > 10 ? 85 : 30; // Occupied vs unoccupied target
      const daylightOffset = daylight * 0.7; // Daylight covers up to 70% of target
      const brightness = isSimulationRunning
        ? Math.round(Math.max(def.minBright, Math.min(100, targetBright - daylightOffset + (zoneOcc > 10 ? 10 : 0))))
        : 75;

      // Status: standby if low occupancy, active otherwise
      const status: Zone['status'] = zoneOcc < 15 ? 'standby' : 'active';

      return { id: def.id, code: def.code, name: def.name, brightness, occupancy: zoneOcc, daylight, status };
    });
  }, [isSimulationRunning, simulatedHour, cloudCover, occupancyPercent, ZONE_DEFS]);

  // Filter sites to only show DALI-enabled buildings
  const daliSites = sites.filter(site => DALI_ENABLED_SITES.includes(site.id));

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
                  DALI Lighting Control
                </h1>
                {isSimulationRunning && (
                  <div className="px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      background: 'rgba(250, 204, 21, 0.15)',
                      color: '#FACC15',
                    }}
                  >
                    💡 Live • {cloudCover?.toFixed(0)}% cloud
                  </div>
                )}
              </div>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {isSimulationRunning 
                  ? `Real-time daylight from simulation • Hour ${simulatedHour}:00 (Day ${daysSimulated}/365)`
                  : 'Wardew Tridonic Integration'
                }
              </p>
            </div>
          </div>
          <BuildingSelector
            sites={daliSites}
            value={selectedSiteId}
            onChange={setSelectedSiteId}
          />
        </div>
      </div>

      {/* Zone Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {zones.map((zone) => (
          <DALIZoneCard key={zone.id} zone={zone} />
        ))}
      </div>
    </div>
  );
}

// DALI Zone Card Component
function DALIZoneCard({ zone }: { zone: Zone }) {
  const [brightness, setBrightness] = useState(zone.brightness);

  const handleBrightnessChange = async (newBrightness: number) => {
    setBrightness(newBrightness);
    // TODO: Call API to update brightness
    // await fetch(`/api/zones/${zone.id}/brightness`, { 
    //   method: 'POST', 
    //   body: JSON.stringify({ brightness: newBrightness }) 
    // });
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
          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
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
        <Metric
          icon={<Lightbulb className="w-4 h-4" style={{ color: "#FACC15" }} />}
          label="Brightness"
          value={`${brightness}%`}
        />
        <Metric
          icon={<Users className="w-4 h-4" style={{ color: "#3B82F6" }} />}
          label="Occupancy"
          value={`${zone.occupancy}%`}
        />
        <Metric
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

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
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
