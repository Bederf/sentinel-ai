import {
  QueryClient,
  MutationCache,
  QueryCache,
} from "@tanstack/react-query";

/**
 * Global React Query client configuration
 *
 * Handles:
 * - Default stale/cache times
 * - Rate limit retry logic (exponential backoff for 429 errors)
 * - Error handling and logging
 * - Request deduplication through cache
 */

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000, // 30s default - data fresh for 30s
      gcTime: 5 * 60 * 1000, // 5m - keep in cache 5m after all observers unsubscribe
      retry: (failureCount, error: unknown) => {
        // 429 errors: retry up to 3 times with exponential backoff
        if (
          error instanceof Error &&
          error.message.includes("429")
        ) {
          return failureCount < 3;
        }
        // Network errors: retry once
        if (
          error instanceof Error &&
          error.message.includes("Network")
        ) {
          return failureCount < 1;
        }
        // Other errors: don't retry
        return false;
      },
      retryDelay: (attemptIndex: number) => {
        // Exponential backoff: 1s, 2s, 4s
        return Math.min(1000 * 2 ** attemptIndex, 30000);
      },
      refetchOnWindowFocus: false, // Prevent refetch when user returns to tab
      refetchOnReconnect: true, // Refetch when internet reconnects
    },
    mutations: {
      retry: false, // Don't retry mutations - they modify state
    },
  },
  queryCache: new QueryCache({
    onError: (error) => {
      // Log query errors to console in dev mode
      if (import.meta.env.DEV) {
        console.error("Query error:", error);
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      // Log mutation errors to console in dev mode
      if (import.meta.env.DEV) {
        console.error("Mutation error:", error);
      }
    },
  }),
});
