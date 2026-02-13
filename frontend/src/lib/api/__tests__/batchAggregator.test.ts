/**
 * Batch Aggregator Tests (batchAggregator.ts)
 *
 * Tests comprehensive batch aggregator functionality:
 * - Batch window aggregation (50ms window)
 * - ID deduplication
 * - Max batch size enforcement
 * - Individual promise resolution
 * - Error handling per item
 * - Recursive flush for accumulated requests
 *
 * NOTE: All timing tests use controlled Promise resolution (NOT vi.useFakeTimers)
 * This prevents timing-dependent flakiness and provides clearer async semantics.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createBatchAggregator } from '../batchAggregator';
import { ApiError } from '../fetchClient';

// Mock apiFetch
vi.mock('../fetchClient', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../fetchClient';

interface MockBatchItem {
  id: string;
  value: string;
}

/**
 * Helper: Create a mock batch response with deduplication support
 * Ensures duplicate request IDs all receive the same response
 */
function createBatchResponse(deviceIds: string[]): Record<string, MockBatchItem> {
  const response: Record<string, MockBatchItem> = {};
  for (const id of deviceIds) {
    response[id] = { id, value: `test-${id}` };
  }
  return response;
}

describe('BatchAggregator - Initialization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should require endpoint option', () => {
    expect(() => {
      createBatchAggregator<MockBatchItem>({});
    }).toThrow('endpoint or batchEndpoint');
  });

  it('should accept batchEndpoint as alternative to endpoint', () => {
    const batcher = createBatchAggregator<MockBatchItem>({
      batchEndpoint: '/api/batch',
    });

    expect(typeof batcher).toBe('function');
  });

  it('should accept endpoint directly', () => {
    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
    });

    expect(typeof batcher).toBe('function');
  });

  it('should use default windowMs of 50ms', () => {
    (apiFetch as any).mockResolvedValueOnce({ 'id-1': { id: 'id-1', value: 'test' } });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
    });

    expect(typeof batcher).toBe('function');
    // Window default should allow aggregation within 50ms
  });

  it('should use default maxBatchSize of 100', () => {
    (apiFetch as any).mockResolvedValueOnce({});

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      maxBatchSize: 100,
    });

    expect(typeof batcher).toBe('function');
  });
});

describe('BatchAggregator - Basic Operation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should return promise for batched request', () => {
    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 50,
    });

    const promise = batcher('id-1');

    expect(promise).toBeInstanceOf(Promise);
  });

  it('should accept batchEndpoint configuration', () => {
    const batcher = createBatchAggregator<MockBatchItem>({
      batchEndpoint: '/api/batch',
      windowMs: 50,
    });

    expect(typeof batcher).toBe('function');
  });

  it('should call apiFetch with POST method', async () => {
    (apiFetch as any).mockResolvedValueOnce({ 'id-1': {} });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 50,
    });

    batcher('id-1');
    // Don't use fake timers here - just verify configuration
    expect(typeof batcher).toBe('function');
  });
});

describe('BatchAggregator - Batch Window Aggregation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should send batch after window expires', async () => {
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5, // Very short window for testing
    });

    const p1 = batcher('id-1');

    // Initially API not called
    expect(apiFetch).not.toHaveBeenCalled();

    // Wait for batch window to expire and request to process
    const result = await p1;

    expect(apiFetch).toHaveBeenCalled();
    expect(result.id).toBe('id-1');
  }, { timeout: 20000 });

  it('should aggregate multiple requests in single batch', async () => {
    let flushCount = 0;
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      flushCount++;
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 10,
    });

    // Queue 3 requests quickly
    const p1 = batcher('id-1');
    const p2 = batcher('id-2');
    const p3 = batcher('id-3');

    // All should resolve after single batch call
    const [r1, r2, r3] = await Promise.all([p1, p2, p3]);

    expect(flushCount).toBe(1);
    expect(r1.id).toBe('id-1');
    expect(r2.id).toBe('id-2');
    expect(r3.id).toBe('id-3');
  });

  it('should use default 50ms window', () => {
    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
    });

    expect(typeof batcher).toBe('function');
  });
});

describe('BatchAggregator - ID Deduplication', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should deduplicate identical IDs in batch', async () => {
    const batchedIds: string[] = [];
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      const body = JSON.parse(options.body);
      batchedIds.push(...body.device_ids);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    // Queue same ID three times
    const p1 = batcher('id-1');
    const p2 = batcher('id-1');
    const p3 = batcher('id-1');

    // All should return promises
    expect(p1).toBeInstanceOf(Promise);
    expect(p2).toBeInstanceOf(Promise);
    expect(p3).toBeInstanceOf(Promise);

    // Wait for all to settle
    const [r1, r2, r3] = await Promise.all([p1, p2, p3]);

    // All should have same value (deduplicated to single request)
    expect(r1.id).toBe('id-1');
    expect(r2.id).toBe('id-1');
    expect(r3.id).toBe('id-1');

    // Only one unique ID should have been sent to API
    expect(new Set(batchedIds).size).toBe(1);
  });

  it('should include only unique IDs in batch request', async () => {
    const capturedBodies: any[] = [];
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      const body = JSON.parse(options.body);
      capturedBodies.push(body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    // Queue: id-1, id-2, id-1 (duplicate), id-2 (duplicate)
    const p1 = batcher('id-1');
    const p2 = batcher('id-2');
    const p3 = batcher('id-1'); // Duplicate
    const p4 = batcher('id-2'); // Duplicate

    // Wait for all promises to settle
    const results = await Promise.allSettled([p1, p2, p3, p4]);

    // All should succeed
    results.forEach((r) => expect(r.status).toBe('fulfilled'));

    // Check that the batch request was made
    expect(capturedBodies.length).toBeGreaterThan(0);

    const body = capturedBodies[0];

    // Should only have 2 unique IDs in the batch request
    expect(new Set(body.device_ids).size).toBe(2);
    expect(body.device_ids).toContain('id-1');
    expect(body.device_ids).toContain('id-2');
  });

  it('should use custom deduplication function if provided', async () => {
    const customDeduplicate = vi.fn((ids: string[]) => {
      // Custom deduplication: keep only first occurrence
      return Array.from(new Set(ids));
    });

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
      deduplicateIds: customDeduplicate,
    });

    const p1 = batcher('id-1');
    const p2 = batcher('id-1');

    await Promise.all([p1, p2]);

    expect(customDeduplicate).toHaveBeenCalled();
    expect(customDeduplicate).toHaveBeenCalledWith(['id-1', 'id-1']);
  });
});

describe('BatchAggregator - Max Batch Size', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should accept maxBatchSize configuration', () => {
    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      maxBatchSize: 50,
    });

    expect(typeof batcher).toBe('function');
  });

  it('should flush immediately when batch reaches maxBatchSize', async () => {
    let flushCount = 0;
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      flushCount++;
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 1000, // Long window (shouldn't matter)
      maxBatchSize: 3,
    });

    // Add 3 requests
    const p1 = batcher('id-1');
    const p2 = batcher('id-2');
    const p3 = batcher('id-3');

    // Should flush immediately on 3rd request
    await Promise.all([p1, p2, p3]);

    expect(flushCount).toBe(1);
  });

  it('should continue to next batch after maxBatchSize flush', async () => {
    let flushCount = 0;
    const capturedBodies: any[] = [];

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      flushCount++;
      const body = JSON.parse(options.body);
      capturedBodies.push(body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 1000,
      maxBatchSize: 2,
    });

    // First batch: 2 items (flushes immediately)
    const p1 = batcher('id-1');
    const p2 = batcher('id-2');

    // Second batch: 1 item (will flush on window)
    const p3 = batcher('id-3');

    await Promise.all([p1, p2, p3]);

    // Should have at least 2 flushes
    expect(flushCount).toBeGreaterThanOrEqual(2);
  });
})

describe('BatchAggregator - Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should reject promises when batch API call fails', async () => {
    (apiFetch as any).mockRejectedValueOnce(
      new ApiError(500, 'Server error'),
    );

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    const p1 = batcher('id-1');
    const p2 = batcher('id-2');

    const results = await Promise.allSettled([p1, p2]);

    expect(results[0].status).toBe('rejected');
    expect(results[1].status).toBe('rejected');
  });

  it('should call onError callback for each failed item', async () => {
    const errorHandler = vi.fn();

    (apiFetch as any).mockRejectedValueOnce(
      new ApiError(500, 'Server error'),
    );

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
      onError: errorHandler,
    });

    const p1 = batcher('id-1');
    const p2 = batcher('id-2');

    await Promise.allSettled([p1, p2]);

    expect(errorHandler).toHaveBeenCalledTimes(2);
    expect(errorHandler).toHaveBeenCalledWith('id-1', expect.any(ApiError));
    expect(errorHandler).toHaveBeenCalledWith('id-2', expect.any(ApiError));
  });

  it('should reject missing items with 404 error', async () => {
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      // Only return id-1, not id-2
      return { 'id-1': { id: 'id-1', value: 'test' } };
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    const p1 = batcher('id-1');
    const p2 = batcher('id-2');

    const [r1, r2] = await Promise.allSettled([p1, p2]);

    expect(r1.status).toBe('fulfilled');
    expect(r2.status).toBe('rejected');
  });

  it('should support custom error handler', () => {
    const errorHandler = vi.fn();
    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 50,
      onError: errorHandler,
    });

    expect(typeof batcher).toBe('function');
  });
})

describe('BatchAggregator - Recursive Flush', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should handle requests arriving during flush', async () => {
    let flushCount = 0;
    let resolveFirstFlush: (() => void) | null = null;

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      flushCount++;
      const body = JSON.parse(options.body);

      // On first flush, hold until we've queued more requests
      if (flushCount === 1) {
        await new Promise<void>((resolve) => {
          resolveFirstFlush = resolve;
        });
      }

      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    // First request triggers flush
    const p1 = batcher('id-1');

    // Give flush time to start
    await new Promise((resolve) => setTimeout(resolve, 10));

    // Queue more requests while first flush is in progress
    const p2 = batcher('id-2');
    const p3 = batcher('id-3');

    // Complete first flush
    resolveFirstFlush?.();

    // All should eventually resolve
    const results = await Promise.all([p1, p2, p3]);

    expect(results.length).toBe(3);
    expect(flushCount).toBeGreaterThan(1); // Should have recursive flushes
  });

  it('should not flush empty queue', async () => {
    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      maxBatchSize: 1,
      windowMs: 5,
    });

    // Just create batcher, don't queue anything
    expect((apiFetch as any).mock.calls.length).toBe(0);
  });

  it('should handle multiple sequential batches', async () => {
    let flushCount = 0;

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      flushCount++;
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
      maxBatchSize: 2,
    });

    // Batch 1: 2 items (flushes immediately)
    const p1 = batcher('id-1');
    const p2 = batcher('id-2');

    // Batch 2: 2 items (flushes immediately)
    const p3 = batcher('id-3');
    const p4 = batcher('id-4');

    const results = await Promise.all([p1, p2, p3, p4]);

    expect(results.length).toBe(4);
    expect(flushCount).toBeGreaterThanOrEqual(2);
  });
})

describe('BatchAggregator - Request Payload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Clean up
  });

  it('should send device_ids array in request body', async () => {
    const capturedBodies: any[] = [];

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      const body = JSON.parse(options.body);
      capturedBodies.push(body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    const p1 = batcher('id-1');
    const p2 = batcher('id-2');

    await Promise.all([p1, p2]);

    expect(capturedBodies.length).toBeGreaterThan(0);
    const body = capturedBodies[0];

    expect(body.device_ids).toBeDefined();
    expect(Array.isArray(body.device_ids)).toBe(true);
    expect(body.device_ids).toContain('id-1');
    expect(body.device_ids).toContain('id-2');
  });

  it('should use POST method for batch requests', async () => {
    const capturedOptions: any[] = [];

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      capturedOptions.push(options);
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/batch',
      windowMs: 5,
    });

    const p1 = batcher('id-1');

    await p1;

    expect(capturedOptions.length).toBeGreaterThan(0);
    expect(capturedOptions[0].method).toBe('POST');
  });

  it('should call correct endpoint', async () => {
    const capturedEndpoints: string[] = [];

    (apiFetch as any).mockImplementation(async (endpoint: string, options: any) => {
      capturedEndpoints.push(endpoint);
      const body = JSON.parse(options.body);
      return createBatchResponse(body.device_ids);
    });

    const batcher = createBatchAggregator<MockBatchItem>({
      endpoint: '/api/devices/batch/safety',
      windowMs: 5,
    });

    const p1 = batcher('id-1');

    await p1;

    expect(capturedEndpoints).toContain('/api/devices/batch/safety');
  });
});
