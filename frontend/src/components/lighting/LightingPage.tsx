/**
 * LightingPage Component - DALI Lighting Control Page
 *
 * Shows Tridonic DALI zone lighting with:
 * - Zone grid with brightness, occupancy, daylight metrics
 * - Manual brightness override sliders
 * - Zone status (active, standby, fault)
 * - Real-time occupancy and daylight data
 *
 * Used as dedicated page accessible via sidebar navigation.
 */

import { useState, useEffect } from 'react';
import { Lightbulb, Sun, Users, Activity } from 'lucide-react';

interface Zone {
  id: string;
  code: string;
  name: string;
  brightness: number;
  occupancy: number;
  daylight: number;
  status: 'active' | 'standby' | 'fault';
}

export function LightingPage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchZoneData();
    const interval = setInterval(fetchZoneData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const fetchZoneData = async () => {
    try {
      // Mock zones data - in production would fetch from /api/zones
      const mockZones: Zone[] = [
        {
          id: 'zone-001',
          code: 'S002-DALI-001',
          name: 'Level 0 - Reception',
          brightness: 85,
          occupancy: 45,
          daylight: 72,
          status: 'active',
        },
        {
          id: 'zone-002',
          code: 'S002-DALI-002',
          name: 'Level 0 - Meeting Room A',
          brightness: 90,
          occupancy: 80,
          daylight: 60,
          status: 'active',
        },
        {
          id: 'zone-003',
          code: 'S002-DALI-003',
          name: 'Level 1 - Open Plan',
          brightness: 75,
          occupancy: 65,
          daylight: 55,
          status: 'active',
        },
        {
          id: 'zone-004',
          code: 'S002-DALI-101',
          name: 'Level 1 - Office Block',
          brightness: 80,
          occupancy: 70,
          daylight: 50,
          status: 'active',
        },
        {
          id: 'zone-005',
          code: 'S002-DALI-102',
          name: 'Level 1 - Conference',
          brightness: 88,
          occupancy: 90,
          daylight: 45,
          status: 'active',
        },
        {
          id: 'zone-006',
          code: 'S002-DALI-201',
          name: 'Level 2 - Admin',
          brightness: 78,
          occupancy: 40,
          daylight: 35,
          status: 'active',
        },
        {
          id: 'zone-007',
          code: 'S002-DALI-202',
          name: 'Level 2 - IT Room',
          brightness: 95,
          occupancy: 15,
          daylight: 10,
          status: 'standby',
        },
        {
          id: 'zone-008',
          code: 'S002-DALI-203',
          name: 'Level 2 - Archive',
          brightness: 50,
          occupancy: 5,
          daylight: 5,
          status: 'standby',
        },
      ];

      setZones(mockZones);
    } catch (error) {
      console.error('Failed to load zones:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="p-4">Loading DALI zones...</div>;
  }

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 rounded" style={{ background: "rgba(250, 204, 21, 0.15)" }}>
            <Lightbulb className="h-6 w-6" style={{ color: "#FACC15" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              DALI Lighting Control
            </h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Wardew Tridonic Integration — Site-002 Sandton Office Complex
            </p>
          </div>
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
