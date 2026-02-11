import { useState, useEffect } from 'react';
import api from '@/lib/api';
import type { DashboardStats } from '@/lib/api';

/**
 * Custom hook to fetch dashboard stats with auto-refetch every 30 seconds
 * Ensures stats stay fresh without manual page refresh
 */
export function useDashboardStats() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadStats = async () => {
      try {
        setLoading(true);
        const statsData = await api.getStats();
        setStats(statsData);
        setError(null);
      } catch (err) {
        console.error('Failed to load dashboard stats:', err);
        setError('Failed to load stats');
      } finally {
        setLoading(false);
      }
    };

    // Load immediately
    loadStats();

    // Set up interval to refetch every 30 seconds
    const interval = setInterval(loadStats, 30 * 1000);

    // Cleanup interval on unmount
    return () => clearInterval(interval);
  }, []);

  return { stats, loading, error };
}
