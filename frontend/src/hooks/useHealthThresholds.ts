import { useState, useEffect } from "react";
import api from '@/lib/api';
import type { SiteThresholds } from '@/lib/api';

export interface HealthThresholds {
  healthy: number;
  warning: number;
  critical: number;
}

/** Legacy hook — fetches health thresholds only. */
export function useHealthThresholds(siteId?: string) {
  const [thresholds, setThresholds] = useState<HealthThresholds>({
    healthy: 85,
    warning: 65,
    critical: 40,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchThresholds = async () => {
      try {
        const data = await api.getHealthThresholds(siteId);
        setThresholds(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch health thresholds:", err);
        setError("Failed to load health thresholds");
      } finally {
        setLoading(false);
      }
    };

    setLoading(true);
    fetchThresholds();
  }, [siteId]);

  const updateThresholds = async (newThresholds: HealthThresholds) => {
    try {
      const updated = await api.updateHealthThresholds(newThresholds, siteId);
      setThresholds(updated);
      setError(null);
      return true;
    } catch (err: any) {
      console.error("Failed to update health thresholds:", err);
      setError(err.message || "Failed to update health thresholds");
      return false;
    }
  };

  return { thresholds, loading, error, updateThresholds };
}

/** Canonical hook — fetches health + risk thresholds from the unified endpoint. */
export function useSiteThresholds(siteId?: string) {
  const [thresholds, setThresholds] = useState<SiteThresholds>({
    health: { healthy: 85, warning: 65, critical: 40 },
    risk: { medium: 31, high: 61, critical: 81 },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchThresholds = async () => {
      try {
        const data = await api.getSiteThresholds(siteId);
        setThresholds(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch site thresholds:", err);
        setError("Failed to load site thresholds");
      } finally {
        setLoading(false);
      }
    };

    setLoading(true);
    fetchThresholds();
  }, [siteId]);

  const updateSiteThresholds = async (newThresholds: SiteThresholds) => {
    try {
      const updated = await api.updateSiteThresholds(newThresholds, siteId);
      setThresholds(updated);
      setError(null);
      return true;
    } catch (err: any) {
      console.error("Failed to update site thresholds:", err);
      setError(err.message || "Failed to update site thresholds");
      return false;
    }
  };

  return { thresholds, loading, error, updateSiteThresholds };
}
