/**
 * OCCUPANCY SYNC HOOK
 *
 * Syncs frontend occupancy simulation with live SimulationContext data.
 * Uses simulated occupancy percentage to drive zone-level occupancy targets.
 *
 * Flow:
 * 1. Get simulation time and occupancy% from SimulationContext (polling every 3s)
 * 2. Calculate zone occupancy from total occupancy percent
 * 3. Update OccupancySimulation targets for each zone
 * 4. Automatically spawn/despawn people based on targets
 * 5. Keep 3D animation in sync with backend simulation
 */

import { useEffect } from 'react';
import type { OccupancySimulation } from '@/lib/occupancySimulation';
import type React from 'react';
import { useSimulation } from '@/contexts/SimulationContext';

interface UseOccupancySyncOptions {
  buildingId: string;
  simulationRef: React.RefObject<OccupancySimulation | null>;
  enabled: boolean;
}

/**
 * Hook for syncing frontend occupancy simulation with SimulationContext
 *
 * Uses live occupancy percentage from simulation to update zone targets.
 * Ensures 3D animation stays in sync with backend lifecycle simulation.
 */
export function useOccupancySync({
  buildingId,
  simulationRef,
  enabled,
}: UseOccupancySyncOptions) {
  // Get live occupancy data from SimulationContext
  const { running, occupancyPercent, simulatedTime, daysSimulated } = useSimulation();

  // Update simulation with live targets from SimulationContext
  useEffect(() => {
    if (!simulationRef.current || !enabled || !running) return;

    const simulation = simulationRef.current;
    const totalOccupancy = occupancyPercent || 0;

    // Default zone configuration (5 zones distributed across building)
    const zones = [
      { zoneId: 'zone-1', name: 'Open Office L1', floor: 0, max: 80 },
      { zoneId: 'zone-2', name: 'Conference L1', floor: 0, max: 30 },
      { zoneId: 'zone-3', name: 'Lobby L0', floor: -1, max: 50 },
      { zoneId: 'zone-4', name: 'Open Office L2', floor: 1, max: 100 },
      { zoneId: 'zone-5', name: 'Meeting Rooms L2', floor: 1, max: 40 },
    ];

    const totalMaxOccupancy = zones.reduce((sum, z) => sum + z.max, 0);

    // Distribute total occupancy across zones proportionally
    for (const zone of zones) {
      const zoneOccupancy = Math.round((zone.max / totalMaxOccupancy) * totalOccupancy);
      
      simulation.updateZoneTarget({
        zoneId: zone.zoneId,
        targetOccupancy: zoneOccupancy,
        maxOccupancy: zone.max,
        personas: {
          worker: 0.7,
          security: 0.1,
          cleaner: 0.1,
          visitor: 0.1,
        },
      });
    }
  }, [occupancyPercent, running, enabled, simulationRef]);

  return {
    isLoading: false,
    simulationTime: simulatedTime ? new Date(simulatedTime) : null,
    totalOccupancy: occupancyPercent || 0,
    dayType: daysSimulated > 180 ? 'weekend' : 'weekday', // Simple heuristic
    occupancyTrend: (occupancyPercent || 0) > 70 ? 'peak' : 'offpeak',
  };
}

export default useOccupancySync;
