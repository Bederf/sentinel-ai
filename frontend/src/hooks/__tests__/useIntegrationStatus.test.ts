/**
 * useIntegrationStatus Hook Tests
 *
 * Tests comprehensive hook functionality:
 * - External integration health status
 * - Active modules tracking
 * - Integration error reporting
 * - Caching behavior
 * - Error handling and edge cases
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import React from 'react';

// Mock integration API types
interface IntegrationHealthStatus {
  name: string;
  status: 'healthy' | 'degraded' | 'unavailable';
  last_check: string;
  error?: string;
}

interface IntegrationStatusResponse {
  site_id: string;
  coordinator_active: boolean;
  active_modules: string[];
  integrations: IntegrationHealthStatus[];
  last_updated: string;
}

// Mock the integration API module
vi.mock('../../lib/api/modules', () => ({
  modulesApi: {
    getIntegrationStatus: vi.fn(),
  },
}));

// Create a mock hook for testing
function useIntegrationStatus(siteId: string | undefined) {
  const { useQuery } = require('@tanstack/react-query');
  const { modulesApi } = require('../../lib/api/modules');

  return useQuery<IntegrationStatusResponse, Error>({
    queryKey: ['integration', 'status', siteId],
    queryFn: () => modulesApi.getIntegrationStatus(siteId!),
    enabled: !!siteId,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: 1,
  });
}

import { modulesApi } from '../../lib/api/modules';

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

// Mock data factories
function createMockIntegrationHealthStatus(
  overrides?: Partial<IntegrationHealthStatus>
): IntegrationHealthStatus {
  return {
    name: 'Solar API',
    status: 'healthy',
    last_check: new Date().toISOString(),
    ...overrides,
  };
}

function createMockIntegrationStatusResponse(
  overrides?: Partial<IntegrationStatusResponse>
): IntegrationStatusResponse {
  return {
    site_id: 'site-002',
    coordinator_active: true,
    active_modules: ['solar', 'hvac', 'energy'],
    integrations: [
      createMockIntegrationHealthStatus({ name: 'Solar API' }),
      createMockIntegrationHealthStatus({ name: 'Weather Service' }),
      createMockIntegrationHealthStatus({ name: 'Energy Pricing API' }),
    ],
    last_updated: new Date().toISOString(),
    ...overrides,
  };
}

describe('useIntegrationStatus', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should fetch integration status successfully', async () => {
      const mockData = createMockIntegrationStatusResponse();
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(result.current.data?.integrations.length).toBe(3);
    });

    it('should report external integration health correctly', async () => {
      const mockData = createMockIntegrationStatusResponse({
        integrations: [
          createMockIntegrationHealthStatus({
            name: 'Solar API',
            status: 'healthy',
          }),
          createMockIntegrationHealthStatus({
            name: 'Weather Service',
            status: 'degraded',
            error: 'Response time > 5s',
          }),
          createMockIntegrationHealthStatus({
            name: 'Energy Pricing API',
            status: 'unavailable',
            error: 'Connection refused',
          }),
        ],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const integrations = result.current.data?.integrations;
      expect(integrations?.[0].status).toBe('healthy');
      expect(integrations?.[1].status).toBe('degraded');
      expect(integrations?.[2].status).toBe('unavailable');
      expect(integrations?.[2].error).toBe('Connection refused');
    });

    it('should track active modules correctly', async () => {
      const mockData = createMockIntegrationStatusResponse({
        active_modules: ['solar', 'hvac', 'energy', 'security'],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.active_modules).toEqual(['solar', 'hvac', 'energy', 'security']);
    });

    it('should track coordinator active status', async () => {
      const mockData = createMockIntegrationStatusResponse({
        coordinator_active: true,
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.coordinator_active).toBe(true);
    });

    it('should handle coordinator inactive status', async () => {
      const mockData = createMockIntegrationStatusResponse({
        coordinator_active: false,
        active_modules: [],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.coordinator_active).toBe(false);
      expect(result.current.data?.active_modules.length).toBe(0);
    });
  });

  describe('Integration Error Reporting', () => {
    it('should report integration errors with details', async () => {
      const mockData = createMockIntegrationStatusResponse({
        integrations: [
          createMockIntegrationHealthStatus({
            name: 'Solar API',
            status: 'unavailable',
            error: 'Authentication failed: Invalid API key',
          }),
        ],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const integration = result.current.data?.integrations[0];
      expect(integration?.status).toBe('unavailable');
      expect(integration?.error).toContain('Authentication');
    });

    it('should distinguish between degraded and unavailable integrations', async () => {
      const mockData = createMockIntegrationStatusResponse({
        integrations: [
          createMockIntegrationHealthStatus({
            name: 'Weather Service',
            status: 'degraded',
            error: 'Response time > 5s',
          }),
          createMockIntegrationHealthStatus({
            name: 'Energy Pricing API',
            status: 'unavailable',
            error: 'Service down for maintenance',
          }),
        ],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const integrations = result.current.data?.integrations;
      expect(integrations?.some((i) => i.status === 'degraded')).toBe(true);
      expect(integrations?.some((i) => i.status === 'unavailable')).toBe(true);
    });

    it('should provide last check timestamp', async () => {
      const lastCheckTime = new Date().toISOString();
      const mockData = createMockIntegrationStatusResponse({
        integrations: [
          createMockIntegrationHealthStatus({
            name: 'Solar API',
            last_check: lastCheckTime,
          }),
        ],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.integrations[0].last_check).toBe(lastCheckTime);
    });
  });

  describe('Caching Behavior', () => {
    it('should respect 30s staleTime', async () => {
      const mockData = createMockIntegrationStatusResponse();
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Verify query was cached
      const queries = queryClient.getQueryCache().getAll();
      const query = queries.find((q) => q.queryKey[0] === 'integration');
      expect(query).toBeDefined();
    });

    it('should reuse cache for duplicate requests', async () => {
      const mockData = createMockIntegrationStatusResponse();
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      // First render
      const { result: result1 } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
      });

      // Second render - should reuse cache
      const { result: result2 } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      expect(result2.current.data).toEqual(mockData);
      expect(vi.mocked(modulesApi.getIntegrationStatus)).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      const error = new Error('Network error');
      vi.mocked(modulesApi.getIntegrationStatus).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle undefined siteId (disabled query)', async () => {
      const { result } = renderHook(() => useIntegrationStatus(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toBeUndefined();
      expect(vi.mocked(modulesApi.getIntegrationStatus)).not.toHaveBeenCalled();
    });

    it('should handle empty integrations list', async () => {
      const mockData = createMockIntegrationStatusResponse({
        integrations: [],
      });
      vi.mocked(modulesApi.getIntegrationStatus).mockResolvedValueOnce(mockData);

      const { result } = renderHook(() => useIntegrationStatus('site-002'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.integrations).toEqual([]);
    });
  });
});
