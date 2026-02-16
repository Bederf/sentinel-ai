/**
 * ZONE CONFIGURATION FOR OCCUPANCY SIMULATION
 *
 * Defines the building's spatial layout with coordinates,
 * capacities, and zone types used for occupancy visualization.
 *
 * This is the user's custom zone configuration from the Grant DALI simulation.
 */

import type { ZoneConfig } from './occupancySimulation';

// Define zones with pixel coordinates (scale: 1px ≈ 0.5cm)
export const OCCUPANCY_ZONES: ZoneConfig[] = [
  {
    id: 'reception',
    name: 'Reception',
    x: 40,
    y: 60,
    w: 180,
    h: 100,
    maxOccupancy: 6,
    type: 'entry',
    floor: 0,
  },
  {
    id: 'openplan-a',
    name: 'Open Plan A',
    x: 240,
    y: 60,
    w: 260,
    h: 140,
    maxOccupancy: 24,
    type: 'office',
    floor: 0,
  },
  {
    id: 'openplan-b',
    name: 'Open Plan B',
    x: 240,
    y: 220,
    w: 260,
    h: 140,
    maxOccupancy: 20,
    type: 'office',
    floor: 0,
  },
  {
    id: 'meeting-1',
    name: 'Boardroom',
    x: 520,
    y: 60,
    w: 140,
    h: 100,
    maxOccupancy: 10,
    type: 'meeting',
    floor: 0,
  },
  {
    id: 'meeting-2',
    name: 'Meeting Room 2',
    x: 520,
    y: 180,
    w: 140,
    h: 80,
    maxOccupancy: 6,
    type: 'meeting',
    floor: 0,
  },
  {
    id: 'meeting-3',
    name: 'Meeting Room 3',
    x: 520,
    y: 280,
    w: 140,
    h: 80,
    maxOccupancy: 6,
    type: 'meeting',
    floor: 0,
  },
  {
    id: 'kitchen',
    name: 'Kitchen',
    x: 40,
    y: 180,
    w: 180,
    h: 90,
    maxOccupancy: 8,
    type: 'common',
    floor: 0,
  },
  {
    id: 'server',
    name: 'Server Room',
    x: 40,
    y: 290,
    w: 100,
    h: 70,
    maxOccupancy: 1,
    type: 'utility',
    floor: 0,
  },
  {
    id: 'bathroom',
    name: 'Restrooms',
    x: 160,
    y: 290,
    w: 60,
    h: 70,
    maxOccupancy: 4,
    type: 'utility',
    floor: 0,
  },
  {
    id: 'corridor',
    name: 'Corridor',
    x: 240,
    y: 370,
    w: 420,
    h: 30,
    maxOccupancy: 5,
    type: 'corridor',
    floor: 0,
  },
];

/**
 * Get zone by ID
 */
export function getZoneById(id: string): ZoneConfig | undefined {
  return OCCUPANCY_ZONES.find(z => z.id === id);
}

/**
 * Get zones by type
 */
export function getZonesByType(type: ZoneConfig['type']): ZoneConfig[] {
  return OCCUPANCY_ZONES.filter(z => z.type === type);
}

/**
 * Get zones on floor
 */
export function getZonesByFloor(floor: number): ZoneConfig[] {
  return OCCUPANCY_ZONES.filter(z => z.floor === floor);
}

/**
 * Get random zone (for destination selection)
 */
export function getRandomZone(): ZoneConfig {
  return OCCUPANCY_ZONES[Math.floor(Math.random() * OCCUPANCY_ZONES.length)];
}

/**
 * Get random zone of specific type
 */
export function getRandomZoneOfType(type: ZoneConfig['type']): ZoneConfig | undefined {
  const zones = getZonesByType(type);
  return zones.length > 0 ? zones[Math.floor(Math.random() * zones.length)] : undefined;
}

/**
 * Calculate total building capacity
 */
export function getTotalCapacity(): number {
  return OCCUPANCY_ZONES.reduce((sum, zone) => sum + zone.maxOccupancy, 0);
}

/**
 * Occupancy patterns per zone type across the day
 * Values are fractions of maxOccupancy (0-1)
 * Based on Grant DALI simulation patterns
 */
export const OCCUPANCY_CURVES: Record<ZoneConfig['type'], number[]> = {
  office: [0, 0, 0.05, 0.3, 0.7, 0.9, 0.95, 0.5, 0.85, 0.9, 0.85, 0.7, 0.4, 0.15, 0.05, 0, 0, 0],
  meeting: [0, 0, 0, 0.1, 0.5, 0.7, 0.8, 0.2, 0.6, 0.8, 0.7, 0.5, 0.3, 0.1, 0, 0, 0, 0],
  common: [0, 0, 0.02, 0.2, 0.4, 0.3, 0.3, 0.8, 0.7, 0.3, 0.3, 0.4, 0.3, 0.1, 0.02, 0, 0, 0],
  utility: [0, 0, 0, 0.1, 0.2, 0.2, 0.3, 0.3, 0.3, 0.2, 0.2, 0.2, 0.1, 0.05, 0, 0, 0, 0],
  corridor: [0, 0, 0.05, 0.3, 0.4, 0.3, 0.3, 0.6, 0.5, 0.3, 0.3, 0.4, 0.3, 0.2, 0.05, 0, 0, 0],
  entry: [0, 0, 0.05, 0.3, 0.4, 0.3, 0.3, 0.6, 0.5, 0.3, 0.3, 0.4, 0.3, 0.2, 0.05, 0, 0, 0],
};

/**
 * Get occupancy for a zone at a specific time
 * @param zone - Zone configuration
 * @param timeIndex - Hour of day (0-17, representing 05:00-22:00)
 * @returns Occupancy fraction (0-1)
 */
export function getOccupancyForZone(zone: ZoneConfig, timeIndex: number): number {
  const curve = OCCUPANCY_CURVES[zone.type] || OCCUPANCY_CURVES.office;
  const base = curve[timeIndex] || 0;
  // Add slight jitter for realism
  const jitter = (Math.random() - 0.5) * 0.15;
  return Math.max(0, Math.min(1, base + jitter));
}

/**
 * Time labels for 18-hour simulation day
 * Format: "HH:MM"
 */
export const TIME_LABELS = [
  '05:00', '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00',
  '13:00', '14:00', '15:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00', '22:00',
];

/**
 * Calculate lighting level based on occupancy ratio
 * Returns: 0 (off) to 1 (full brightness)
 */
export function getLightLevel(occupancyRatio: number): number {
  if (occupancyRatio <= 0.02) return 0;
  if (occupancyRatio < 0.15) return 0.25;
  if (occupancyRatio < 0.4) return 0.55;
  if (occupancyRatio < 0.7) return 0.8;
  return 1.0;
}

/**
 * Calculate HVAC state based on occupancy ratio
 */
export function getHvacState(occupancyRatio: number): 'off' | 'setback' | 'active' {
  if (occupancyRatio <= 0.02) return 'off';
  if (occupancyRatio < 0.3) return 'setback';
  return 'active';
}
