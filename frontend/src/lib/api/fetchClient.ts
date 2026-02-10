/**
 * Standard error class for API errors with status codes
 */
export class ApiError extends Error {
  public status: number;
  public data?: unknown;

  constructor(
    status: number,
    message: string,
    data?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

const ACCESS_TOKEN_KEY = 'sentinel_token';

async function parseErrorResponse(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return await response.text();
  }
}

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
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  const headers = new Headers(options.headers || {});
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const body = options.body
    ? typeof options.body === 'string' ? options.body : JSON.stringify(options.body)
    : undefined;

  try {
    const response = await fetch(url, { ...options, headers, body });

    if (!response.ok) {
      const data = await parseErrorResponse(response);
      throw new ApiError(response.status, `HTTP ${response.status}`, data);
    }

    try {
      return await response.json() as T;
    } catch {
      return {} as T;
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      error instanceof Error ? error.message : 'Unknown error',
      error,
    );
  }
}
