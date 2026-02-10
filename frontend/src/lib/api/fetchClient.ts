/**
 * Standard error class for API errors with status codes
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public data?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const ACCESS_TOKEN_KEY = 'sentinel_token';

/**
 * Single fetch function for all API requests
 * Handles:
 * - Auth token retrieval from localStorage
 * - JSON serialization/parsing
 * - Standard error normalization
 * - No rate limiting (React Query handles caching + deduplication)
 *
 * @param url - API endpoint URL
 * @param options - Fetch options (method, body, headers, etc.)
 * @returns Parsed JSON response
 * @throws ApiError on HTTP error status or network failure
 */
export async function apiFetch<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  // Get auth token from localStorage
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);

  // Build headers
  const headers = new Headers(options.headers || {});
  headers.set('Content-Type', 'application/json');

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  // Serialize body if provided
  let body: string | undefined;
  if (options.body) {
    body = typeof options.body === 'string'
      ? options.body
      : JSON.stringify(options.body);
  }

  // Execute fetch
  try {
    const response = await fetch(url, {
      ...options,
      headers,
      body,
    });

    // Handle non-2xx responses
    if (!response.ok) {
      let data: unknown;
      try {
        data = await response.json();
      } catch {
        // If response isn't JSON, use text
        data = await response.text();
      }

      throw new ApiError(
        response.status,
        `HTTP ${response.status}: ${response.statusText}`,
        data,
      );
    }

    // Parse successful response
    try {
      return await response.json() as T;
    } catch {
      // If response isn't JSON, return empty object
      return {} as T;
    }
  } catch (error) {
    // Re-throw ApiError as-is
    if (error instanceof ApiError) {
      throw error;
    }

    // Wrap other errors
    throw new ApiError(
      0,
      error instanceof Error ? error.message : 'Unknown error',
      error,
    );
  }
}
