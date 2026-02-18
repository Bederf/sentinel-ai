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
