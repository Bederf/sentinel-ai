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
 * - Automatic retry on rate limit (429) errors with exponential backoff
 * - React Query handles caching + deduplication
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

  // Retry configuration for rate limit errors
  const maxRetries = 3;
  let delay = 500; // Start with 500ms
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, { ...options, headers, body });

      if (!response.ok) {
        const data = await parseErrorResponse(response);
        
        // Handle rate limit errors with retry
        if (response.status === 429 && attempt < maxRetries) {
          console.warn(`Rate limit hit (429), retrying in ${delay}ms... (attempt ${attempt + 1}/${maxRetries})`);
          await new Promise(resolve => setTimeout(resolve, delay));
          delay *= 2; // Exponential backoff
          continue; // Retry
        }
        
        throw new ApiError(response.status, `HTTP ${response.status}`, data);
      }

      try {
        return await response.json() as T;
      } catch {
        return {} as T;
      }
    } catch (error) {
      // If it's a rate limit error and we haven't exhausted retries, continue to retry
      if (error instanceof ApiError && error.status === 429 && attempt < maxRetries) {
        console.warn(`Rate limit hit (429), retrying in ${delay}ms... (attempt ${attempt + 1}/${maxRetries})`);
        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 2;
        continue;
      }
      
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        0,
        error instanceof Error ? error.message : 'Unknown error',
        error,
      );
    }
  }
  
  throw new ApiError(429, 'Rate limit exceeded after retries');
}
