/**
 * React Query Test Utilities
 * Provides configuration and wrappers for testing React Query hooks
 */

import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';

/**
 * Create a test-specific QueryClient with appropriate defaults for testing
 * - No retry on failures
 * - Infinite cache time to prevent GC during tests
 * - Synchronous behavior for predictable test timing
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity, // Previously cacheTime
        staleTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

/**
 * Create a wrapper component that provides QueryClientProvider
 * Use with renderHook(hook, { wrapper: createQueryWrapper() })
 */
export function createQueryWrapper() {
  const queryClient = createTestQueryClient();

  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

/**
 * Alternative: Higher-order component style wrapper
 * For use with render() instead of renderHook()
 */
export function withQueryClient(component: ReactElement) {
  const queryClient = createTestQueryClient();

  return React.createElement(QueryClientProvider, { client: queryClient }, component);
}

/**
 * Clear all caches in the test client
 * Useful for isolating tests
 */
export function clearQueryCache(queryClient: QueryClient) {
  queryClient.clear();
}

/**
 * Manually set query data for a specific key
 * Useful for pre-populating cache before running tests
 */
export function setQueryData<T>(
  queryClient: QueryClient,
  queryKey: unknown[],
  data: T
) {
  queryClient.setQueryData(queryKey, data);
}

/**
 * Get query data from the cache
 * Useful for asserting cached values
 */
export function getQueryData(queryClient: QueryClient, queryKey: unknown[]) {
  return queryClient.getQueryData(queryKey);
}

/**
 * Invalidate a query to trigger a refetch
 * Useful for testing refetch behavior
 */
export async function invalidateQuery(
  queryClient: QueryClient,
  queryKey: unknown[]
) {
  await queryClient.invalidateQueries({ queryKey });
}

/**
 * Create a wrapper component that provides both QueryClient AND ModuleContext
 * Use with render(component, { wrapper: createModuleContextWrapper() })
 *
 * This enables testing of module-dependent components without context errors
 */
export function createModuleContextWrapper(
  moduleContextValue?: React.ComponentProps<
    typeof import('../contexts/ModuleContext').ModuleProvider
  >
) {
  const queryClient = createTestQueryClient();
  const { ModuleProvider } = require('../contexts/ModuleContext');

  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(
        ModuleProvider,
        { initialSiteId: 'test-site', initialSiteName: 'Test Site', ...moduleContextValue },
        children
      )
    );
  };
}
