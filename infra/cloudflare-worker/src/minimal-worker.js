/**
 * AimTheLaw Minimal Cloudflare Worker
 * Non-breaking performance enhancement layer
 * Preserves ALL existing infrastructure and functionality
 */

// Minimal security headers (complementing existing Caddy headers)
const MINIMAL_SECURITY_HEADERS = {
  'X-Powered-By': 'AimTheLaw-Edge',
  'X-Cache-Status': 'CLOUDFLARE'
};

// Only cache these explicitly safe endpoints (very conservative)
// These work for both staging AND production
const SAFE_CACHE_PATHS = [
  '/health',
  '/api/health',
  '/api/lawyers',        // Public lawyer directory (no auth required)
  '/api/status',         // System status
  '/api/public/info',    // Public information endpoint
  '/api/public/contact'  // Public contact info
];

// Cache durations (conservative) - same for staging and production
const CACHE_DURATIONS = {
  '/health': 60,                // 1 minute
  '/api/health': 60,            // 1 minute
  '/api/lawyers': 300,          // 5 minutes (public data)
  '/api/status': 30,            // 30 seconds
  '/api/public/info': 600,      // 10 minutes (static info)
  '/api/public/contact': 600    // 10 minutes (contact details)
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    try {
      // Handle caching only for explicitly safe endpoints
      if (shouldCache(url.pathname, request.method)) {
        return await handleCachedRequest(request, env, url);
      }

      // For everything else, pass through unchanged to preserve existing behavior
      return await passThrough(request);

    } catch (error) {
      // If anything goes wrong, always fall back to direct origin
      console.error('Worker error, falling back to origin:', error);
      return await passThrough(request);
    }
  }
};

/**
 * Determine if request should be cached (very conservative approach)
 */
function shouldCache(pathname, method) {
  // Only cache GET requests
  if (method !== 'GET') return false;

  // Only cache explicitly whitelisted paths
  return SAFE_CACHE_PATHS.includes(pathname);
}

/**
 * Handle cacheable requests with fallback to origin
 */
async function handleCachedRequest(request, env, url) {
  const cacheKey = `safe-cache:${url.pathname}`;
  const cacheDuration = CACHE_DURATIONS[url.pathname] || 60;

  try {
    // Try to get from cache first (if KV is available)
    let cachedResponse = null;
    if (env.MY_APP_STORAGE) {
      cachedResponse = await env.MY_APP_STORAGE.get(cacheKey);
    }

    if (cachedResponse) {
      return new Response(cachedResponse, {
        headers: {
          ...MINIMAL_SECURITY_HEADERS,
          'Content-Type': 'application/json',
          'Cache-Control': `public, max-age=${cacheDuration}`,
          'X-Cache': 'HIT'
        }
      });
    }

    // Cache miss - fetch from origin
    const originResponse = await passThrough(request);

    // Only cache successful responses
    if (originResponse.ok && originResponse.status === 200) {
      const responseText = await originResponse.text();

      // Store in cache with TTL (if KV is available)
      if (env.MY_APP_STORAGE) {
        try {
          await env.MY_APP_STORAGE.put(cacheKey, responseText, {
            expirationTtl: cacheDuration
          });
        } catch (kvError) {
          console.error('KV storage error (non-critical):', kvError);
        }
      }

      return new Response(responseText, {
        status: originResponse.status,
        headers: {
          ...Object.fromEntries(originResponse.headers),
          ...MINIMAL_SECURITY_HEADERS,
          'X-Cache': 'MISS'
        }
      });
    }

    // Return origin response unchanged if not cacheable
    return originResponse;

  } catch (cacheError) {
    // If caching fails, always fall back to origin
    console.error('Cache error, falling back to origin:', cacheError);
    return await passThrough(request);
  }
}

/**
 * Pass request through to origin unchanged (preserves all existing behavior)
 */
async function passThrough(request) {
  // Forward request exactly as received
  const originResponse = await fetch(request);

  // Return response with minimal additional headers
  return new Response(originResponse.body, {
    status: originResponse.status,
    statusText: originResponse.statusText,
    headers: {
      ...Object.fromEntries(originResponse.headers),
      ...MINIMAL_SECURITY_HEADERS
    }
  });
}

/**
 * Optional: Minimal audit logging (only for cached requests)
 */
async function logCacheEvent(env, event, path, ip) {
  try {
    // Only log cache-related events (minimal logging)
    if (env.MY_APP_DATABASE) {
      await env.MY_APP_DATABASE.prepare(
        'INSERT INTO cache_stats (endpoint, event_type, timestamp) VALUES (?, ?, ?)'
      ).bind(path, event, Date.now()).run();
    }
  } catch (error) {
    // Logging failure should never affect main functionality
    console.error('Logging failed (non-critical):', error);
  }
}
