import { useCallback, useEffect, useState } from "react";

import { authorizedFetch } from "@/lib/api";

export interface SpaceRoomStateRow {
  room_code: string;
  site_id: string;
  occupied: boolean;
}

export interface SpaceRoomsLiveSummary {
  roomCount: number;
  occupiedCount: number;
  loading: boolean;
  error: string | null;
  fetchedAt: Date | null;
  refresh: () => Promise<void>;
}

const POLL_MS = 20000;

/**
 * Polls `/api/space/rooms` for live room state. Enabled only for site-001 (Fairlands POC).
 */
export function useSpaceRoomsLiveIndicator(siteId: string | undefined): SpaceRoomsLiveSummary {
  const enabled = siteId === "site-001";
  const [rooms, setRooms] = useState<SpaceRoomStateRow[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  const fetchRooms = useCallback(async () => {
    if (!enabled || !siteId) return;
    try {
      const res = await authorizedFetch(`/api/space/rooms?site_id=${encodeURIComponent(siteId)}`, {
        headers: { "x-site-id": siteId },
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const json = (await res.json()) as SpaceRoomStateRow[];
      setRooms(Array.isArray(json) ? json : []);
      setFetchedAt(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Room state unavailable");
    } finally {
      setLoading(false);
    }
  }, [enabled, siteId]);

  useEffect(() => {
    if (!enabled) {
      setRooms([]);
      setLoading(false);
      setError(null);
      setFetchedAt(null);
      return;
    }
    void fetchRooms();
    const id = window.setInterval(() => void fetchRooms(), POLL_MS);
    return () => window.clearInterval(id);
  }, [enabled, fetchRooms]);

  const occupiedCount = rooms.filter((r) => r.occupied).length;

  return {
    roomCount: rooms.length,
    occupiedCount,
    loading,
    error,
    fetchedAt,
    refresh: fetchRooms,
  };
}
