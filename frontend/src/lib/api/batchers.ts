import {
  createBatchAggregator,
} from "./batchAggregator";
import type {
  DeviceSafetyStatus,
  DeviceStatus,
  DeviceCondition,
} from "./types";

/**
 * Batch aggregators for device data
 *
 * Instances:
 * - safetyBatcher: Groups safety-status requests (50ms window)
 * - readingsBatcher: Groups latest-readings requests (50ms window)
 * - conditionBatcher: Groups condition requests (50ms window)
 */

export const safetyBatcher = createBatchAggregator<DeviceSafetyStatus>(
  {
    batchEndpoint: "/api/devices/batch/safety-status",
    windowMs: 50,
    maxBatchSize: 100,
  }
);

export const readingsBatcher = createBatchAggregator<DeviceStatus>(
  {
    batchEndpoint: "/api/devices/batch/latest-readings",
    windowMs: 50,
    maxBatchSize: 100,
  }
);

export const conditionBatcher = createBatchAggregator<DeviceCondition>(
  {
    batchEndpoint: "/api/devices/batch/condition",
    windowMs: 50,
    maxBatchSize: 100,
  }
);

/**
 * Batch aggregator for sites (Phase 102 rate limiting fix)
 *
 * Prevents 429 errors when multiple dashboard components request site data simultaneously.
 * Groups requests over 50ms window and sends to POST /api/sites/batch
 */
export const sitesBatcher = createBatchAggregator<any>(
  {
    batchEndpoint: "/api/sites/batch",
    windowMs: 50,
    maxBatchSize: 100,
  }
);

/**
 * Solar overview request debouncer
 *
 * Prevents 429 rate limit errors when multiple solar components request overview simultaneously.
 * Caches responses for 2 seconds to deduplicate identical requests.
 * Sends sequential requests (300ms delay between) instead of parallel.
 */
const solarOverviewCache = new Map<string, { data: any; timestamp: number }>();
const solarOverviewQueue: Array<{
  siteId: string;
  resolve: (data: any) => void;
  reject: (error: any) => void;
}> = [];
let solarOverviewProcessing = false;

async function processSolarOverviewQueue() {
  if (solarOverviewProcessing || solarOverviewQueue.length === 0) {
    return;
  }

  solarOverviewProcessing = true;

  while (solarOverviewQueue.length > 0) {
    const { siteId, resolve, reject } = solarOverviewQueue.shift()!;

    try {
      // Check cache first
      const cached = solarOverviewCache.get(siteId);
      if (cached && Date.now() - cached.timestamp < 2000) {
        resolve(cached.data);
      } else {
        // Fetch from API
        const { fetchSolarOverview } = await import("@/lib/solarApi");
        const data = await fetchSolarOverview(siteId);
        solarOverviewCache.set(siteId, { data, timestamp: Date.now() });
        resolve(data);
      }
    } catch (error) {
      reject(error);
    }

    // Delay between requests to avoid rate limiting
    if (solarOverviewQueue.length > 0) {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }

  solarOverviewProcessing = false;
}

export async function solarOverviewBatcher(siteId: string): Promise<any> {
  return new Promise((resolve, reject) => {
    solarOverviewQueue.push({ siteId, resolve, reject });
    processSolarOverviewQueue();
  });
}
