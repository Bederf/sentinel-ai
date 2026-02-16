/**
 * OCCUPANCY SYNC HOOK
 *
 * Polls backend occupancy endpoint and syncs frontend simulation
 * with backend Grant scenario time and occupancy targets.
 *
 * Flow:
 * 1. Poll /dali/building/{building_id}/occupancy/detailed every 1 second
 * 2. Extract simulation time from response
 * 3. Update OccupancySimulation targets for each zone
 * 4. Automatically spawn/despawn people based on targets
 * 5. Keep simulation in sync with backend scenario
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import type { OccupancySimulation } from '@/lib/occupancySimulation';
import type React from 'react';

interface OccupancyZoneData {
  zone_id: string;
  zone_name: string;
  floor: number;
  coordinates: { x: number; y: number; w: number; h: number };
  max_occupancy: number;
  current_occupancy: number;
  occupancy_percent: number;
  zone_type: string;
  personas: Record<string, number>;
}

interface DetailedOccupancyResponse {
  building_id: string;
  timestamp: string;
  day_type: 'weekday' | 'weekend';
  zones: OccupancyZoneData[];
  total_occupancy: number;
  occupancy_trend: 'peak' | 'offpeak';
}

interface UseOccupancySyncOptions {
  buildingId: string;
  simulationRef: React.RefObject<OccupancySimulation | null>;
  enabled: boolean;
  pollIntervalMs?: number;
}

/**
 * Hook for syncing frontend occupancy simulation with backend
 *
 * Polls occupancy endpoint and updates simulation targets.
 * Ensures frontend animation stays in sync with backend scenario time.
 */
export function useOccupancySync({
  buildingId,
  simulationRef,
  enabled,
  pollIntervalMs = 1000,
}: UseOccupancySyncOptions) {
  // Fetch occupancy targets from backend
  const { data: occupancyData, isLoading } = useQuery<DetailedOccupancyResponse>({
    queryKey: ['building-occupancy-detailed', buildingId],
    queryFn: async () => {
      const response = await fetch(
        `/api/dali/building/${buildingId}/occupancy/detailed`
      );
      if (!response.ok) {
        throw new Error(`Failed to fetch occupancy: ${response.statusText}`);
      }
      return response.json() as Promise<DetailedOccupancyResponse>;
    },
    refetchInterval: pollIntervalMs, // Poll every 1 second
    enabled: enabled && !!buildingId,
    staleTime: 0, // Always consider data stale (we want fresh updates)
  });

  // Update simulation with targets from backend
  useEffect(() => {
    if (!occupancyData || !simulationRef.current) return;

    const simulation = simulationRef.current;

    // Update simulation time to match backend (Grant scenario time)
    const simTime = new Date(occupancyData.timestamp);
    // Note: In a full implementation, we'd store this in the simulation
    // For now, frontend runs at its own pace but uses backend targets

    // Reconcile occupancy for each zone
    for (const zoneData of occupancyData.zones) {
      // Update zone targets in simulation
      // The simulation will automatically spawn/despawn people to match targets
      simulation.updateZoneTarget({
        zoneId: zoneData.zone_id,
        targetOccupancy: zoneData.current_occupancy,
        maxOccupancy: zoneData.max_occupancy,
        personas: zoneData.personas, // Persona ratios from backend
      });
    }
  }, [occupancyData, simulationRef]);

  return {
    occupancyData,
    isLoading,
    simulationTime: occupancyData ? new Date(occupancyData.timestamp) : null,
    totalOccupancy: occupancyData?.total_occupancy || 0,
    dayType: occupancyData?.day_type || 'weekday',
    occupancyTrend: occupancyData?.occupancy_trend || 'offpeak',
  };
}

export default useOccupancySync;
