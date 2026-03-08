import { apiFetch, ApiError } from './fetchClient';
/* eslint-disable @typescript-eslint/no-unused-vars */

/**
 * Options for batch aggregator factory
 */
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - T is part of the generic interface signature
export interface BatchAggregatorOptions<T> {
  /** API endpoint to POST batched IDs to */
  endpoint?: string;
  /** API endpoint to POST batched IDs to (alternative name) */
  batchEndpoint?: string;
  /** Time window in ms to collect requests before sending batch (default: 50ms) */
  windowMs?: number;
  /** Maximum batch size (enforces flush when reached) */
  maxBatchSize?: number;
  /** Optional function to deduplicate IDs (default: Set-based) */
  deduplicateIds?: (ids: string[]) => string[];
  /** Optional error handler (called per item with error) */
  onError?: (id: string, error: ApiError) => void;
}

/**
 * Item in the request queue
 */
interface QueuedRequest<T> {
  id: string;
  resolve: (value: T) => void;
  reject: (error: Error) => void;
}

/**
 * Process successful batch response and resolve/reject promises
 */
function processResponse<T>(
  current: QueuedRequest<T>[],
  response: Record<string, T>,
  onError: ((id: string, error: ApiError) => void) | undefined,
) {
  for (const request of current) {
    const result = response[request.id];
    if (result !== undefined) {
      request.resolve(result);
    } else {
      // Item not found in response
      const error = new ApiError(404, `Item not found: ${request.id}`);
      onError?.(request.id, error);
      request.reject(error);
    }
  }
}

/**
 * Handle batch error and reject all requests
 */
function handleBatchError<T>(
  current: QueuedRequest<T>[],
  error: unknown,
  onError: ((id: string, error: ApiError) => void) | undefined,
) {
  const apiError = error instanceof ApiError
    ? error
    : new ApiError(0, error instanceof Error ? error.message : 'Unknown error');

  for (const request of current) {
    onError?.(request.id, apiError);
    request.reject(apiError);
  }
}

/**
 * Factory function to create a batch aggregator
 *
 * Features:
 * - Collects requests within 50ms window (configurable)
 * - Deduplicates IDs before batch call
 * - Fires ONE POST to batch endpoint with all IDs
 * - Resolves each Promise individually
 * - Recursive flush for accumulated requests
 * - Per-item error tracking
 *
 * @param options - Configuration for the batch aggregator
 * @returns Function to add requests to the batch
 *
 * @example
 * const safetyBatcher = createBatchAggregator<DeviceSafetyStatus>({
 *   endpoint: '/api/devices/batch/safety',
 *   windowMs: 50,
 * });
 *
 * // Later, queue a request
 * const status = await safetyBatcher('device-123');
 */
export function createBatchAggregator<BatchItem>(
  options: BatchAggregatorOptions<BatchItem>,
) {
  const {
    endpoint = options.batchEndpoint,
    windowMs = 50,
    maxBatchSize = 100,
    deduplicateIds = (ids) => Array.from(new Set(ids)),
    onError,
  } = options;

  if (!endpoint) {
    throw new Error('BatchAggregatorOptions requires endpoint or batchEndpoint');
  }

  const resolvedEndpoint: string = endpoint;

  // Queue of pending requests
  let queue: QueuedRequest<BatchItem>[] = [];
  // Timer for batch flush
  let flushTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * Flush the batch queue - sends one POST request with all IDs
   */
  async function flush() {
    // Take snapshot of current queue
    const current = queue;
    queue = [];

    if (current.length === 0) {
      return;
    }

    // Extract and deduplicate IDs
    const ids = current.map((r) => r.id);
    const uniqueIds = deduplicateIds(ids);

    try {
      // POST to batch endpoint with all IDs
      const response = await apiFetch<Record<string, BatchItem>>(resolvedEndpoint, {
        method: 'POST',
        body: JSON.stringify({ device_ids: uniqueIds }),
      });

      processResponse(current, response, onError);
    } catch (error) {
      handleBatchError(current, error, onError);
    }

    // Recursive flush if more requests accumulated while processing
    if (queue.length > 0) {
      await flush();
    }
  }

  /**
   * Add a request to the batch queue
   */
  function addRequest(id: string): Promise<BatchItem> {
    return new Promise((resolve, reject) => {
      queue.push({ id, resolve, reject });

      // Flush immediately if batch reaches maxBatchSize
      if (queue.length >= maxBatchSize) {
        if (flushTimer !== null) {
          clearTimeout(flushTimer);
          flushTimer = null;
        }
        flush().catch((error) => {
          console.error('Batch flush failed:', error);
        });
      } else if (flushTimer === null) {
        // Schedule flush if not already scheduled
        flushTimer = setTimeout(() => {
          flushTimer = null;
          flush().catch((error) => {
            console.error('Batch flush failed:', error);
          });
        }, windowMs);
      }
    });
  }

  return addRequest;
}
