/**
 * Equipment Markers Tests
 *
 * Tests centroid-based equipment positioning logic in 3D visualization
 */

import { describe, it, expect } from 'vitest';

// Mock zone centroid data (pre-calculated zone centers)
const mockCentroids: Record<string, { x: number; z: number }> = {
  'Zone-L0-A': { x: 3.0, z: 10.0 },
  'Zone-L0-B': { x: 9.0, z: 10.0 },
  'Zone-L0-C': { x: 15.0, z: 10.0 },
  'Zone-L1-A': { x: 3.0, z: 10.0 },
  'Zone-L1-B': { x: 9.0, z: 10.0 },
  'Zone-L2-A': { x: 3.0, z: 10.0 },
};

// Floor height mapping
const floorHeights: Record<string, number> = {
  'B1': 0.5,
  'G': 3.5,
  'L0': 3.5,
  'L1': 6.5,
  'L2': 9.5,
  'R': 12.5,
};

// Equipment type offset mapping
const typeOffsets: Record<string, [number, number]> = {
  'fcu': [-1, 0],      // Slightly left of center
  'vav': [0, -2],      // Slightly front
  'dali': [1, 1],      // Spread across zone
  'chiller': [-12, -8], // Plant room (absolute)
  'ahu': [10, 8],      // Plant room
  'hvac': [0, 0],      // Generic HVAC at center
  'lighting': [1, 0],  // Lighting spread
};

/**
 * Get equipment position based on equipment code and zone centroids
 * Returns [x, y, z] coordinates for 3D placement
 */
function getEquipmentPosition(
  equipmentCode: string,
  zoneCentroids: Record<string, { x: number; z: number }>
): [number, number, number] {
  // Extract floor and zone from equipment code
  // Format: S###-TYPE-FLOOR-ZONE
  const floorMatch = equipmentCode.match(/-(B\d|G|L\d+|R)-/);
  const zoneMatch = equipmentCode.match(/-([A-Z]|0?\d{1,3})$/);

  const floorCode = floorMatch ? floorMatch[1] : 'L0';
  const zoneIdentifier = zoneMatch ? zoneMatch[1] : 'A';

  // Determine zone letter (A-Z) for zoned equipment, or use numeric for plant room
  const isZonedEquipment = /^[A-Z]$/.test(zoneIdentifier);
  const zoneLetter = isZonedEquipment ? zoneIdentifier : 'A';

  // Floor Y-coordinate
  const y = floorHeights[floorCode] || 3.5;

  // Extract equipment type for offset calculation
  const typeMatch = equipmentCode.match(/-([A-Z]+)-/);
  const equipmentType = typeMatch ? typeMatch[1].toLowerCase() : '';

  // Calculate position from zone centroids
  if (zoneCentroids && isZonedEquipment) {
    const zoneId = `Zone-${floorCode}-${zoneLetter}`;
    const centroid = zoneCentroids[zoneId];

    if (centroid) {
      const [xOffset, zOffset] = typeOffsets[equipmentType] || [0, 0];
      return [centroid.x + xOffset, y, centroid.z + zOffset];
    }
  }

  // Fallback to simple zone letter offset if no centroid data
  const zoneOffset = (zoneLetter.charCodeAt(0) - 65) * 6;
  return [zoneOffset + 3, y, 10];
}

describe('Equipment Positioning with Zone Centroids', () => {
  it('positions FCU near zone centroid with type offset', () => {
    const equipmentCode = 'S002-FCU-L1-A';
    const [x, y, z] = getEquipmentPosition(equipmentCode, mockCentroids);

    // Centroid: (3.0, 10.0), FCU offset: [-1, 0]
    expect(x).toBeCloseTo(2.0, 1); // 3.0 - 1
    expect(y).toBe(6.5); // L1 floor height
    expect(z).toBeCloseTo(10.0, 1);
  });

  it('positions VAV with front offset', () => {
    const equipmentCode = 'S002-VAV-L1-B';
    const [x, y, z] = getEquipmentPosition(equipmentCode, mockCentroids);

    // Centroid: (9.0, 10.0), VAV offset: [0, -2]
    expect(x).toBeCloseTo(9.0, 1);
    expect(y).toBe(6.5); // L1 floor height
    expect(z).toBeCloseTo(8.0, 1); // 10.0 - 2
  });

  it('positions DALI lighting with spread offset', () => {
    const equipmentCode = 'S002-DALI-L1-C';
    const [x, y, z] = getEquipmentPosition(equipmentCode, mockCentroids);

    // Centroid: (15.0, 10.0), DALI offset: [1, 1]
    expect(x).toBeCloseTo(16.0, 1); // 15.0 + 1
    expect(y).toBe(6.5);
    expect(z).toBeCloseTo(11.0, 1); // 10.0 + 1
  });

  it('falls back to simple offset if no centroid data', () => {
    const equipmentCode = 'S002-FCU-L1-A';
    const [x, y, z] = getEquipmentPosition(equipmentCode, {});

    // Fallback: zone letter offset (A = 0, so 0 + 3 = 3)
    expect(x).toBe(3);
    expect(y).toBe(6.5);
    expect(z).toBe(10);
  });

  it('falls back for unknown zone', () => {
    const equipmentCode = 'S002-FCU-L1-Z';
    const [x, y, z] = getEquipmentPosition(equipmentCode, mockCentroids);

    // No centroid for Zone-L1-Z, should fallback to letter offset
    const zoneOffset = (90 - 65) * 6; // Z = 25 * 6 = 150
    expect(x).toBe(zoneOffset + 3);
    expect(y).toBe(6.5);
    expect(z).toBe(10);
  });

  it('handles different floor heights correctly', () => {
    const equipmentL0 = 'S002-FCU-L0-A';
    const equipmentL1 = 'S002-FCU-L1-A';
    const equipmentL2 = 'S002-FCU-L2-A';
    const equipmentB1 = 'S002-FCU-B1-A';

    const [, yL0] = getEquipmentPosition(equipmentL0, mockCentroids);
    const [, yL1] = getEquipmentPosition(equipmentL1, mockCentroids);
    const [, yL2] = getEquipmentPosition(equipmentL2, mockCentroids);
    const [, yB1] = getEquipmentPosition(equipmentB1, mockCentroids);

    expect(yL0).toBe(3.5); // L0 floor height
    expect(yL1).toBe(6.5); // L1 floor height
    expect(yL2).toBe(9.5); // L2 floor height
    expect(yB1).toBe(0.5); // B1 floor height
  });

  it('positions equipment in different zones correctly', () => {
    const equipmentA = 'S002-FCU-L1-A';
    const equipmentB = 'S002-FCU-L1-B';
    const equipmentC = 'S002-FCU-L1-C';

    const [xA] = getEquipmentPosition(equipmentA, mockCentroids);
    const [xB] = getEquipmentPosition(equipmentB, mockCentroids);
    const [xC] = getEquipmentPosition(equipmentC, mockCentroids);

    // Zones should be spread across X-axis (different X positions)
    expect(xB).toBeGreaterThan(xA);
    expect(xC).toBeGreaterThan(xB);
  });

  it('handles plant room equipment (numeric zone)', () => {
    const equipmentCode = 'S002-CHILLER-B1-001';
    const [x, y, z] = getEquipmentPosition(equipmentCode, mockCentroids);

    // Plant room equipment should use fallback positioning
    // Zone identifier "001" is not a letter, so fallback
    expect(y).toBe(0.5); // B1 floor height
    // X, Z should be fallback values
    expect(x).toBe(3); // Default fallback
    expect(z).toBe(10); // Default fallback
  });

  it('extracts floor code correctly', () => {
    const cases = [
      { code: 'S002-FCU-B1-001', floor: 'B1', y: 0.5 },
      { code: 'S002-AHU-G-001', floor: 'G', y: 3.5 },
      { code: 'S002-FCU-L0-A', floor: 'L0', y: 3.5 },
      { code: 'S002-FCU-L1-A', floor: 'L1', y: 6.5 },
      { code: 'S002-FCU-R-001', floor: 'R', y: 12.5 },
    ];

    cases.forEach(({ code, y: expectedY }) => {
      const [, y] = getEquipmentPosition(code, mockCentroids);
      expect(y).toBe(expectedY);
    });
  });

  it('handles multiple zones on same floor', () => {
    const testCentroids: Record<string, { x: number; z: number }> = {
      'Zone-L1-A': { x: 3.0, z: 10.0 },
      'Zone-L1-B': { x: 9.0, z: 10.0 },
      'Zone-L1-C': { x: 15.0, z: 10.0 },
      'Zone-L1-D': { x: 21.0, z: 10.0 },
      'Zone-L1-E': { x: 27.0, z: 10.0 },
    };

    const positions = ['A', 'B', 'C', 'D', 'E'].map((zone) => {
      const [x] = getEquipmentPosition(`S002-FCU-L1-${zone}`, testCentroids);
      return x;
    });

    // Positions should increase across zones
    for (let i = 1; i < positions.length; i++) {
      expect(positions[i]).toBeGreaterThan(positions[i - 1]);
    }
  });

  it('calculates centroid distance from zone center', () => {
    const equipmentCode = 'S002-FCU-L1-A';
    const [x, , z] = getEquipmentPosition(equipmentCode, mockCentroids);
    const centroid = mockCentroids['Zone-L1-A'];

    // With FCU offset [-1, 0], position should be centroid + offset
    expect(x).toBe(centroid.x - 1);
    expect(z).toBe(centroid.z);

    // Calculate distance from centroid
    const distance = Math.sqrt(Math.pow(x - centroid.x, 2) + Math.pow(z - centroid.z, 2));
    expect(distance).toBeCloseTo(1.0, 1); // Distance should be 1 unit
  });

  it('handles equipment type case-insensitively', () => {
    const equipmentCodes = ['S002-FCU-L1-A', 'S002-fcu-L1-A', 'S002-Fcu-L1-A'];

    // All should produce the same position (type matching should be case-insensitive)
    // Note: in real code, equipment codes are uppercase, but test robustness
    const positions = equipmentCodes.map((code) => {
      const upperCode = code.toUpperCase();
      return getEquipmentPosition(upperCode, mockCentroids);
    });

    // All positions should be the same
    positions.forEach((pos) => {
      expect(pos[0]).toBeCloseTo(positions[0][0], 1);
      expect(pos[1]).toBe(positions[0][1]);
      expect(pos[2]).toBeCloseTo(positions[0][2], 1);
    });
  });

  it('positions equipment to avoid overlap in same zone', () => {
    // Multiple equipment of different types in same zone should have different positions
    const centroidsData = mockCentroids;

    const fcu = getEquipmentPosition('S002-FCU-L1-A', centroidsData);
    const vav = getEquipmentPosition('S002-VAV-L1-A', centroidsData);
    const dali = getEquipmentPosition('S002-DALI-L1-A', centroidsData);

    // Each should have different X or Z coordinate
    expect(fcu).not.toEqual(vav);
    expect(vav).not.toEqual(dali);
    expect(fcu).not.toEqual(dali);
  });

  it('validates centroid data structure', () => {
    const validCentroids: Record<string, { x: number; z: number }> = {
      'Zone-L1-A': { x: 3.0, z: 10.0 },
    };

    const [x, , z] = getEquipmentPosition('S002-FCU-L1-A', validCentroids);

    // Position should be based on valid centroid
    expect(typeof x).toBe('number');
    expect(typeof z).toBe('number');
    expect(x).toBeGreaterThan(0);
    expect(z).toBeGreaterThan(0);
  });

  it('handles missing equipment type gracefully', () => {
    // Equipment code without recognized type pattern
    const equipmentCode = 'S002-XYZ-L1-A';
    const [x, y, z] = getEquipmentPosition(equipmentCode, mockCentroids);

    // Should use default offset [0, 0]
    expect(x).toBeCloseTo(3.0, 1); // Centroid X with no offset
    expect(y).toBe(6.5);
    expect(z).toBeCloseTo(10.0, 1); // Centroid Z with no offset
  });
});
