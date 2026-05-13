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
      staleTime: 60 * 1000, // 60s — reduce refetch churn (was 30s)
      gcTime: 10 * 60 * 1000, // 10m — keep in cache longer after unsubscribe (was 5m)
      retry: (failureCount, error: unknown) => {
        // Check for ApiError object structure (status property)
        const apiError = error as { status?: number; message?: string } | null;

        // 429 errors (rate limit): Retry up to 3 times with exponential backoff
        // (apiFetch already handles initial retries, React Query adds extra layer)
        if (apiError?.status === 429) {
          return failureCount < 3;
        }

        // Check Error message string as fallback
        if (
          error instanceof Error &&
          error.message.includes("429")
        ) {
          return failureCount < 3;
        }

        // Network errors: retry up to 2 times
        if (
          error instanceof Error &&
          error.message.includes("NetworkError")
        ) {
          return failureCount < 2;
        }

        // Check for network-related ApiError messages
        if (apiError?.message?.includes("NetworkError")) {
          return failureCount < 2;
        }

        // Other errors: don't retry
        return false;
      },
      retryDelay: (attemptIndex: number) => {
        // Exponential backoff with jitter: 1s, 2s, 4s, 8s
        const baseDelay = Math.min(1000 * 2 ** attemptIndex, 16000);
        // Add random jitter (0-30% of delay) to avoid thundering herd
        const jitter = Math.random() * baseDelay * 0.3;
        return baseDelay + jitter;
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
