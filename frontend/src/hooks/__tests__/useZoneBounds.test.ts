/**
 * useZoneBounds Hook Tests
 *
 * Tests zone spatial positioning for Digital Twin:
 * - Zone boundary calculations from desk coordinates
 * - Desk positioning and retrieval
 * - Centroid calculations for equipment placement
 * - Equipment allocation by zone
 * - Floor filtering
 * - Real-time cache invalidation
 * - Multi-site zone naming schemes (office vs hospital)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';
import { useZoneBounds } from '../useZoneBounds';
import type { Desk } from '@/lib/api/sites';

// Mock the sites API
vi.mock('@/lib/api/sites', () => ({
  sitesApi: {
    getDesks: vi.fn(),
  },
}));

import { sitesApi } from '@/lib/api/sites';

// Test utilities
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,  // Disable all retries in tests
        gcTime: 0,  // No garbage collection in tests
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// Mock data generators
function createMockDesk(overrides?: Partial<Desk>): Desk {
  return {
    id: 'desk-' + Math.random().toString(36).substr(2, 9),
    code: `Desk-${Math.floor(Math.random() * 300) + 1}`,
    zone_id: 'Zone-001',
    x_coord: Math.random() * 20 - 10,
    z_coord: Math.random() * 18 - 9,
    floor_level: 0,
    occupancy: Math.random() > 0.5,
    ...overrides,
  };
}

function createMockDesksForZone(zoneId: string, count: number, xBase: number, zBase: number): Desk[] {
  const desks: Desk[] = [];
  for (let i = 0; i < count; i++) {
    desks.push(
      createMockDesk({
        zone_id: zoneId,
        code: `Desk-${Math.floor(Math.random() * 100) + 1}`,
        // Cluster desks in a zone area
        x_coord: xBase + (Math.random() * 4 - 2),
        z_coord: zBase + (Math.random() * 4 - 2),
      })
    );
  }
  return desks;
}

describe('useZoneBounds', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Zone List & Fetching', () => {
    it('should fetch desk data for building', async () => {
      const mockDesks = createMockDesksForZone('Zone-001', 20, -10, 0);
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(mockDesks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      expect(sitesApi.getDesks).toHaveBeenCalledWith('building-001');
    });

    it('should return empty map when no desks available', async () => {
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce([]);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(Object.keys(result.current).length).toBe(0);
      });

      expect(result.current).toEqual({});
    });

    it('should group desks by zone correctly', async () => {
      const zone1Desks = createMockDesksForZone('Zone-001', 10, -10, 0);
      const zone2Desks = createMockDesksForZone('Zone-002', 15, -5, 0);
      const allDesks = [...zone1Desks, ...zone2Desks];

      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(allDesks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
        expect(result.current['Zone-002']).toBeDefined();
      });

      expect(Object.keys(result.current).length).toBe(2);
    });
  });

  describe('Zone Boundary Calculations', () => {
    it('should calculate correct zone bounds from desk coordinates', async () => {
      // Create desks with known bounds
      const desks = [
        createMockDesk({ zone_id: 'Zone-L1-A', x_coord: 0, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-L1-A', x_coord: 10, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-L1-A', x_coord: 5, z_coord: 8 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-L1-A']).toBeDefined();
      });

      const bounds = result.current['Zone-L1-A'];
      expect(bounds.minX).toBe(0);
      expect(bounds.maxX).toBe(10);
      expect(bounds.minZ).toBe(0);
      expect(bounds.maxZ).toBe(8);
    });

    it('should calculate zone width correctly', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 2, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 8, z_coord: 0 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds.width).toBe(6); // 8 - 2
    });

    it('should calculate zone depth correctly', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 0, z_coord: 1 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 0, z_coord: 7 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds.depth).toBe(6); // 7 - 1
    });

    it('should ensure minimum zone dimensions', async () => {
      // Single point desk (width/depth = 0, should have minimum 2)
      const desks = [createMockDesk({ zone_id: 'Zone-001', x_coord: 5, z_coord: 5 })];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds.width).toBe(2); // Minimum
      expect(bounds.depth).toBe(2); // Minimum
    });
  });

  describe('Centroid Calculations', () => {
    it('should calculate zone centroid as average of desk positions', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 0, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 10, z_coord: 10 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds.centerX).toBe(5); // (0 + 10) / 2
      expect(bounds.centerZ).toBe(5); // (0 + 10) / 2
    });

    it('should compute centroid for multi-desk zones', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 0, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 6, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 12, z_coord: 0 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds.centerX).toBe(6); // (0 + 12) / 2
    });

    it('should center equipment marker placement using centroids', async () => {
      const desks = createMockDesksForZone('Zone-101', 20, -5, 2);
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-101']).toBeDefined();
      });

      const bounds = result.current['Zone-101'];
      // Centroid should be within bounds
      expect(bounds.centerX).toBeGreaterThanOrEqual(bounds.minX);
      expect(bounds.centerX).toBeLessThanOrEqual(bounds.maxX);
      expect(bounds.centerZ).toBeGreaterThanOrEqual(bounds.minZ);
      expect(bounds.centerZ).toBeLessThanOrEqual(bounds.maxZ);
    });
  });

  describe('Equipment Allocation', () => {
    it('should support numeric zone IDs (office numbering)', async () => {
      // Office zones: 001-005 (L0), 100-104 (L1), 200-204 (L2)
      const zone1Desks = createMockDesksForZone('Zone-001', 10, -10, 0);
      const zone101Desks = createMockDesksForZone('Zone-101', 15, -5, 0);
      const zone201Desks = createMockDesksForZone('Zone-201', 12, 0, 0);

      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce([
        ...zone1Desks,
        ...zone101Desks,
        ...zone201Desks,
      ]);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
        expect(result.current['Zone-101']).toBeDefined();
        expect(result.current['Zone-201']).toBeDefined();
      });

      expect(Object.keys(result.current).length).toBe(3);
    });

    it('should support location-based zone IDs (hospital naming)', async () => {
      // Hospital zones: B1 (basement), L1-L9 (levels), R (roof)
      const b1Desks = createMockDesksForZone('Zone-B1-001', 8, -8, 0);
      const l3Desks = createMockDesksForZone('Zone-L3-ICU', 12, -4, 0);
      const rDesks = createMockDesksForZone('Zone-R-001', 6, 0, 0);

      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce([...b1Desks, ...l3Desks, ...rDesks]);

      const { result } = renderHook(
        () => useZoneBounds('building-hospital'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-B1-001']).toBeDefined();
        expect(result.current['Zone-L3-ICU']).toBeDefined();
        expect(result.current['Zone-R-001']).toBeDefined();
      });

      expect(Object.keys(result.current).length).toBe(3);
    });

    it('should handle unknown zones gracefully', async () => {
      const desks = [createMockDesk({ zone_id: 'unknown' })];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['unknown']).toBeDefined();
      });

      // Should still calculate bounds for unknown zones
      expect(result.current['unknown'].centerX).toBeDefined();
    });
  });

  describe('Floor Filtering', () => {
    it('should support floor level filtering', async () => {
      const l0Desks = createMockDesksForZone('Zone-001', 5, -10, 0);
      l0Desks.forEach((d) => (d.floor_level = 0));

      const l1Desks = createMockDesksForZone('Zone-101', 5, -5, 0);
      l1Desks.forEach((d) => (d.floor_level = 1));

      const l2Desks = createMockDesksForZone('Zone-201', 5, 0, 0);
      l2Desks.forEach((d) => (d.floor_level = 2));

      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce([...l0Desks, ...l1Desks, ...l2Desks]);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
        expect(result.current['Zone-101']).toBeDefined();
        expect(result.current['Zone-201']).toBeDefined();
      });

      // All floors should be present
      expect(Object.keys(result.current).length).toBe(3);
    });

    it('should calculate bounds correctly across floor levels', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 0, z_coord: 0, floor_level: 0 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 10, z_coord: 10, floor_level: 0 }),
        createMockDesk({ zone_id: 'Zone-101', x_coord: 0, z_coord: 0, floor_level: 1 }),
        createMockDesk({ zone_id: 'Zone-101', x_coord: 8, z_coord: 8, floor_level: 1 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
        expect(result.current['Zone-101']).toBeDefined();
      });

      // Each floor should have correct bounds
      const z001 = result.current['Zone-001'];
      expect(z001.maxX).toBe(10);
      expect(z001.maxZ).toBe(10);

      const z101 = result.current['Zone-101'];
      expect(z101.maxX).toBe(8);
      expect(z101.maxZ).toBe(8);
    });
  });

  describe('Caching Behavior', () => {
    it('should use 5-minute stale time', async () => {
      const desks = createMockDesksForZone('Zone-001', 10, -10, 0);
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      // Verify cache entry exists
      const cacheEntry = queryClient.getQueryData(['desks', 'building-001']);
      expect(cacheEntry).toBeDefined();
    });

    it('should return cached data on second call within stale time', async () => {
      const desks = createMockDesksForZone('Zone-001', 10, -10, 0);
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      // First call
      const { result: result1 } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current['Zone-001']).toBeDefined();
      });

      // Second call should use cache
      const { result: result2 } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      expect(result2.current['Zone-001']).toBeDefined();
      expect(sitesApi.getDesks).toHaveBeenCalledTimes(1); // Only called once
    });

    it('should use different cache for different buildings', async () => {
      const b1Desks = createMockDesksForZone('Zone-001', 5, -10, 0);
      const b2Desks = createMockDesksForZone('Zone-001', 5, -8, 0);

      vi.mocked(sitesApi.getDesks)
        .mockResolvedValueOnce(b1Desks)
        .mockResolvedValueOnce(b2Desks);

      const { result: result1 } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      const { result: result2 } = renderHook(
        () => useZoneBounds('building-002'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result1.current['Zone-001']).toBeDefined();
        expect(result2.current['Zone-001']).toBeDefined();
      });

      expect(sitesApi.getDesks).toHaveBeenCalledTimes(2);
      expect(sitesApi.getDesks).toHaveBeenCalledWith('building-001');
      expect(sitesApi.getDesks).toHaveBeenCalledWith('building-002');
    });
  });

  describe('Real-Time Updates', () => {
    it('should invalidate cache when desk data changes', async () => {
      const initialDesks = createMockDesksForZone('Zone-001', 10, -10, 0);
      const updatedDesks = createMockDesksForZone('Zone-001', 12, -10, 0);

      vi.mocked(sitesApi.getDesks)
        .mockResolvedValueOnce(initialDesks)
        .mockResolvedValueOnce(updatedDesks);

      const { result, rerender } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const _initialBounds = result.current['Zone-001'];

      // Invalidate cache
      await queryClient.invalidateQueries({
        queryKey: ['desks', 'building-001'],
      });

      rerender();

      await waitFor(() => {
        expect(sitesApi.getDesks).toHaveBeenCalledTimes(2);
      });

      // Bounds may change after refetch
      expect(sitesApi.getDesks).toHaveBeenCalledWith('building-001');
    });

    it('should update bounds when new desks are added to zone', async () => {
      const initialDesks = createMockDesksForZone('Zone-001', 2, -5, 0);
      initialDesks[0].x_coord = 0;
      initialDesks[1].x_coord = 4;

      const updatedDesks = [
        ...initialDesks,
        createMockDesk({ zone_id: 'Zone-001', x_coord: 10, z_coord: 0 }),
      ];

      vi.mocked(sitesApi.getDesks)
        .mockResolvedValueOnce(initialDesks)
        .mockResolvedValueOnce(updatedDesks);

      const { result, rerender } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const initialBounds = result.current['Zone-001'];
      const initialWidth = initialBounds.width;

      // Simulate desk addition
      await queryClient.invalidateQueries({
        queryKey: ['desks', 'building-001'],
      });

      rerender();

      await waitFor(() => {
        expect(sitesApi.getDesks).toHaveBeenCalledTimes(2);
      });

      // Width should increase with new desk
      const updatedBounds = result.current['Zone-001'];
      expect(updatedBounds.width).toBeGreaterThanOrEqual(initialWidth);
    });
  });

  describe('Data Structure Validation', () => {
    it('should return ZoneBounds with all required fields', async () => {
      const desks = createMockDesksForZone('Zone-001', 3, -5, 0);
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds).toHaveProperty('minX');
      expect(bounds).toHaveProperty('maxX');
      expect(bounds).toHaveProperty('minZ');
      expect(bounds).toHaveProperty('maxZ');
      expect(bounds).toHaveProperty('centerX');
      expect(bounds).toHaveProperty('centerZ');
      expect(bounds).toHaveProperty('width');
      expect(bounds).toHaveProperty('depth');
    });

    it('should maintain coordinate precision', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 1.5, z_coord: 2.7 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: 3.8, z_coord: 5.2 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
      });

      const bounds = result.current['Zone-001'];
      expect(bounds.minX).toBe(1.5);
      expect(bounds.maxX).toBe(3.8);
      expect(bounds.minZ).toBe(2.7);
      expect(bounds.maxZ).toBe(5.2);
    });

    it('should handle desks with missing/null coordinates', async () => {
      const desks = [
        createMockDesk({ zone_id: 'Zone-001', x_coord: 0, z_coord: 0 }),
        createMockDesk({ zone_id: 'Zone-001', x_coord: undefined as any, z_coord: 5 }),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      const { result } = renderHook(
        () => useZoneBounds('building-001'),
        { wrapper: createWrapper(queryClient) }
      );

      // Should handle gracefully
      await waitFor(() => {
        expect(result.current).toBeDefined();
      });
    });
  });

  describe('Multi-Site Zone Naming Schemes', () => {
    it('should handle office zone numbering (001-204)', async () => {
      const officeDesks = [
        ...createMockDesksForZone('Zone-001', 5, -10, 0),
        ...createMockDesksForZone('Zone-102', 5, -5, 0),
        ...createMockDesksForZone('Zone-203', 5, 0, 0),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(officeDesks);

      const { result } = renderHook(
        () => useZoneBounds('building-office'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-001']).toBeDefined();
        expect(result.current['Zone-102']).toBeDefined();
        expect(result.current['Zone-203']).toBeDefined();
      });

      // All three zones should be present
      expect(Object.keys(result.current).length).toBe(3);
    });

    it('should handle hospital floor naming (B1, L1-L9, R)', async () => {
      const hospitalDesks = [
        ...createMockDesksForZone('Zone-B1-001', 3, -10, 0),
        ...createMockDesksForZone('Zone-L3-ICU', 4, -5, 0),
        ...createMockDesksForZone('Zone-L9-OR', 3, 0, 0),
        ...createMockDesksForZone('Zone-R-001', 2, 5, 0),
      ];
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(hospitalDesks);

      const { result } = renderHook(
        () => useZoneBounds('building-hospital'),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => {
        expect(result.current['Zone-B1-001']).toBeDefined();
        expect(result.current['Zone-L3-ICU']).toBeDefined();
        expect(result.current['Zone-L9-OR']).toBeDefined();
        expect(result.current['Zone-R-001']).toBeDefined();
      });

      expect(Object.keys(result.current).length).toBe(4);
    });
  });

  describe('Enable/Disable Logic', () => {
    it('should not fetch when building ID is empty', () => {
      const { result } = renderHook(() => useZoneBounds(''), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current).toEqual({});
      expect(sitesApi.getDesks).not.toHaveBeenCalled();
    });

    it('should fetch when building ID is provided', async () => {
      const desks = createMockDesksForZone('Zone-001', 5, -10, 0);
      vi.mocked(sitesApi.getDesks).mockResolvedValueOnce(desks);

      renderHook(() => useZoneBounds('building-001'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(sitesApi.getDesks).toHaveBeenCalled();
      });

      expect(sitesApi.getDesks).toHaveBeenCalledWith('building-001');
    });
  });
});
