import { apiFetch, ApiError } from './fetchClient';

/**
 * Options for batch aggregator factory
 */
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
export function createBatchAggregator<T>(
  options: BatchAggregatorOptions<T>,
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

  // Queue of pending requests
  let queue: QueuedRequest<T>[] = [];
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
      const response = await apiFetch<Record<string, T>>(endpoint, {
        method: 'POST',
        body: JSON.stringify({ ids: uniqueIds }),
      });

      // Resolve each request with its response
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
    } catch (error) {
      // Network error - reject all requests
      const apiError = error instanceof ApiError
        ? error
        : new ApiError(0, error instanceof Error ? error.message : 'Unknown error');

      for (const request of current) {
        onError?.(request.id, apiError);
        request.reject(apiError);
      }
    }

    // Recursive flush if more requests accumulated while processing
    if (queue.length > 0) {
      await flush();
    }
  }

  /**
   * Add a request to the batch queue
   */
  function addRequest(id: string): Promise<T> {
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
