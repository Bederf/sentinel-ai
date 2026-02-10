import { useState, useEffect } from 'react';
import { sitesApi } from '@/lib/api/sites';
import type { Equipment } from '@/lib/api/sites';

/**
 * Fetch real building equipment from Supabase via cached API
 * 
 * Uses sitesApi.getEquipment() which:
 * - Returns equipment array from Supabase
 * - Caches results in Redis for 300s (SEMI_STATIC TTL)
 * - Falls back to JSON files if Supabase unavailable
 * 
 * Refreshes every 5 seconds to keep equipment status current
 */
export function useEquipmentData(buildingId: string) {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchEquipment() {
      if (!buildingId) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const response = await sitesApi.getEquipment(buildingId);
        setEquipment(response.equipment || []);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch equipment:', err);
        setError(err instanceof Error ? err.message : 'Failed to load equipment');
        setEquipment([]);
      } finally {
        setLoading(false);
      }
    }

    fetchEquipment();

    // Refresh every 5 seconds for real-time updates
    // Redis cache (300s TTL) will serve most requests quickly
    const interval = setInterval(fetchEquipment, 5000);
    return () => clearInterval(interval);
  }, [buildingId]);

  return { equipment, loading, error };
}
