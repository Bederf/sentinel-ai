/**
 * Energy Flow Path Utilities
 *
 * Provides path calculation and styling helpers for the AnimatedEnergyFlow
 * component in the Digital Twin 3D view.
 */

import * as THREE from 'three'

/**
 * Calculate an L-shaped path between two 3D positions.
 * Simulates piping/conduit routing: horizontal XZ first, then vertical Y.
 */
export function calculatePathPoints(
  from: [number, number, number],
  to: [number, number, number]
): THREE.Vector3[] {
  const start = new THREE.Vector3(from[0], from[1], from[2])
  const end = new THREE.Vector3(to[0], to[1], to[2])

  // If same floor (similar Y), use a gentle arc via midpoint offset
  const yDiff = Math.abs(end.y - start.y)
  if (yDiff < 0.5) {
    const mid = new THREE.Vector3(
      (start.x + end.x) / 2,
      start.y + 0.3, // slight lift for visual separation
      (start.z + end.z) / 2
    )
    return [start, mid, end]
  }

  // Different floors: L-shaped routing
  // Go horizontal on start floor, then vertical, then horizontal on end floor
  const midX = (start.x + end.x) / 2
  const midZ = (start.z + end.z) / 2

  return [
    start,
    new THREE.Vector3(midX, start.y, midZ),
    new THREE.Vector3(midX, end.y, midZ),
    end,
  ]
}

/** Map flow_type to display colour (hex string). */
export function getFlowColor(flowType: string): string {
  const colors: Record<string, string> = {
    chilled_water_supply: '#2563eb',
    chilled_water_return: '#ef4444',
    electrical: '#f59e0b',
    condensate: '#06b6d4',
  }
  return colors[flowType] || '#94a3b8'
}

/**
 * Calculate animation speed from power in kW.
 * Higher power -> faster particle movement.
 * Returns a multiplier (0.5 - 3.0).
 */
export function getAnimationSpeed(powerKw: number): number {
  if (powerKw <= 0) return 0.5
  // Log scale: 1kW -> ~0.5, 10kW -> ~1.0, 100kW -> ~1.5, 500kW -> ~2.5
  return Math.min(3.0, 0.5 + Math.log10(Math.max(1, powerKw)) * 0.7)
}
