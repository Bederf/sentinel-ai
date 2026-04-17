/**
 * Optimized CloudFlare Worker with Edge-First Caching - PRODUCTION VERSION
 * Eliminates unnecessary KV "not found" reads using:
 * 1. Edge Cache API (free, ultra-fast)
 * 2. KV index for known cached paths
 * 3. Negative caching for 404/410 responses
 */

interface Env {
  MY_APP_STORAGE: KVNamespace;
  RATE_LIMITER?: any;
  AUTH_SECRET?: string;
  ADMIN_TOKEN?: string;
}

// Cache configuration
const INDEX_KEY = "safe-cache:index";           // JSON array of cached pathnames
const CACHE_PREFIX = "safe-cache:";             // KV value prefix
const NEG_PREFIX = "neg:";                      // negative-cache marker
const INDEX_TTL_SECS = 300;                     // edge cache for the index (5 min)
const NEG_TTL_SECS = 600;                       // how long to remember 404s (10 min)

// Security headers
const MINIMAL_SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '1; mode=block',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
};

// Cache durations for different paths (seconds)
const CACHE_DURATIONS: Record<string, number> = {
  '/api/health': 30,
  '/api/config': 300,          // Config changes infrequently
  '/api/static': 3600,         // Static resources
  '/api/clients': 120,         // Client data - moderate frequency
  '/api/lawyers': 120,         // Lawyer data - moderate frequency
  '/api/public': 600,          // Public endpoints - longer cache
  '/api/status': 60            // Status checks
};

// Debug mode control - PRODUCTION: OFF
const DEBUG_HEADERS = false;

// Helper functions for KV operations
async function getIndex(env: Env): Promise<Set<string>> {
  // Cached at the edge via cacheTtl to avoid repeated KV reads
  const raw = await env.MY_APP_STORAGE.get(INDEX_KEY, { cacheTtl: INDEX_TTL_SECS });
  if (!raw) return new Set();
  try {
    return new Set<string>(JSON.parse(raw));
  } catch {
    return new Set();
  }
}

async function addToIndex(env: Env, path: string): Promise<void> {
  // Small namespaces => simple read/modify/write is fine
  const set = await getIndex(env);
  if (set.has(path)) return;

  set.add(path);

  // Keep index size manageable (max 1000 paths)
  if (set.size > 1000) {
    // Remove oldest entries (simple FIFO)
    const arr = Array.from(set);
    const trimmed = arr.slice(-800); // Keep last 800
    await env.MY_APP_STORAGE.put(INDEX_KEY, JSON.stringify(trimmed));
  } else {
    await env.MY_APP_STORAGE.put(INDEX_KEY, JSON.stringify([...set]));
  }
}

function kvKey(pathname: string): string {
  return `${CACHE_PREFIX}${pathname}`;
}

function negKey(pathname: string): string {
  return `${NEG_PREFIX}${pathname}`;
}

// Determine if a path should be cached
function shouldCache(pathname: string): boolean {
  // Only cache whitelisted API paths
  return Object.keys(CACHE_DURATIONS).some(path => pathname.startsWith(path));
}

// Get cache duration for a path
function getCacheDuration(pathname: string): number {
  for (const [path, duration] of Object.entries(CACHE_DURATIONS)) {
    if (pathname.startsWith(path)) {
      return duration;
    }
  }
  return 60; // Default 1 minute
}

// Handle origin request
async function handleOrigin(request: Request): Promise<Response> {
  // Pass through to backend
  const backendUrl = new URL(request.url);
  backendUrl.hostname = 'api.aimthelaw.co.za';

  return fetch(backendUrl.toString(), {
    method: request.method,
    headers: request.headers,
    body: request.body
  });
}

// Main worker
export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    const url = new URL(request.url);

    // Admin cache purge endpoint
    if (url.pathname === '/__cache/purge' && request.method === 'POST') {
      const adminToken = request.headers.get('x-admin-token');
      if (!env.ADMIN_TOKEN || adminToken !== env.ADMIN_TOKEN) {
        return new Response('Forbidden', { status: 403 });
      }

      try {
        const { path } = await request.json();
        if (!path || typeof path !== 'string') {
          return new Response('Invalid path', { status: 400 });
        }

        // Remove from KV cache
        await env.MY_APP_STORAGE.delete(kvKey(path));
        await env.MY_APP_STORAGE.delete(negKey(path));

        // Remove from edge cache
        const cache = caches.default;
        const purgeUrl = new URL(path, url.origin).toString();
        await cache.delete(new Request(purgeUrl, { method: 'GET' }));

        // Update index to remove the path
        const index = await getIndex(env);
        if (index.has(path)) {
          index.delete(path);
          await env.MY_APP_STORAGE.put(INDEX_KEY, JSON.stringify([...index]));
        }

        return new Response(JSON.stringify({
          success: true,
          message: `Cache cleared for ${path}`
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      } catch (error) {
        return new Response(JSON.stringify({
          success: false,
          error: 'Invalid JSON'
        }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' }
        });
      }
    }

    // Skip caching for non-GET requests
    if (request.method !== 'GET') {
      return handleOrigin(request);
    }

    // Skip caching for non-whitelisted paths
    if (!shouldCache(url.pathname)) {
      return handleOrigin(request);
    }

    // 1) Free edge cache first
    const cache = caches.default;
    const cacheKey = new Request(url.toString(), request);
    const cacheHit = await cache.match(cacheKey);

    if (cacheHit) {
      // Clean response - no debug headers in production
      const response = new Response(cacheHit.body, cacheHit);
      response.headers.set('Server-Timing', 'phase;desc="HIT-EDGE"');
      return response;
    }

    // 2) Check negative cache to avoid hammering origin for persistent 404/410
    const neg = await env.MY_APP_STORAGE.get(
      negKey(url.pathname),
      { cacheTtl: INDEX_TTL_SECS }
    );

    if (neg) {
      return new Response('Not found (cached)', {
        status: 404,
        headers: {
          ...MINIMAL_SECURITY_HEADERS,
          'Server-Timing': 'phase;desc="NEG-HIT"'
        }
      });
    }

    // 3) Consult KV-backed index to decide if KV.get is worth it
    const index = await getIndex(env);

    if (index.has(url.pathname)) {
      const cachedBody = await env.MY_APP_STORAGE.get(kvKey(url.pathname));

      if (cachedBody !== null) {
        const headers = new Headers(MINIMAL_SECURITY_HEADERS);
        headers.set('Content-Type', 'application/json');
        headers.set('Server-Timing', 'phase;desc="HIT-KV"');
        headers.set('Cache-Control', `public, max-age=${getCacheDuration(url.pathname)}`);

        const response = new Response(cachedBody, { headers });

        // Hydrate edge cache asynchronously
        ctx.waitUntil(cache.put(cacheKey, response.clone()));

        return response;
      }
      // If index lied (rare), fall through and correct it on write
    }

    // 4) Fetch from origin
    const originRes = await handleOrigin(request);

    // Clone for reading body
    const [resForClient, resForCache] = [originRes.clone(), originRes.clone()];

    // 5) Cache good responses; remember negative ones briefly
    if (originRes.status >= 200 && originRes.status < 300) {
      const body = await resForCache.text();
      const cacheDuration = getCacheDuration(url.pathname);

      // KV write-through
      ctx.waitUntil(
        env.MY_APP_STORAGE.put(kvKey(url.pathname), body, {
          expirationTtl: cacheDuration
        })
      );

      // Update index (edge-cached, small read)
      ctx.waitUntil(addToIndex(env, url.pathname));

      // Create response with proper headers
      const headers = new Headers(resForClient.headers);
      Object.entries(MINIMAL_SECURITY_HEADERS).forEach(([key, value]) => {
        headers.set(key, value);
      });
      headers.set('Cache-Control', `public, max-age=${cacheDuration}, stale-while-revalidate=${cacheDuration * 2}`);
      headers.set('Server-Timing', 'phase;desc="MISS"');

      const finalResponse = new Response(body, {
        status: resForClient.status,
        statusText: resForClient.statusText,
        headers
      });

      // Populate free Edge Cache
      ctx.waitUntil(cache.put(cacheKey, finalResponse.clone()));

      return finalResponse;

    } else if (originRes.status === 404 || originRes.status === 410) {
      // Negative caching to stop repeated misses
      ctx.waitUntil(
        env.MY_APP_STORAGE.put(negKey(url.pathname), '1', {
          expirationTtl: NEG_TTL_SECS
        })
      );
    }

    // Return origin response with security headers
    const headers = new Headers(resForClient.headers);
    Object.entries(MINIMAL_SECURITY_HEADERS).forEach(([key, value]) => {
      headers.set(key, value);
    });
    headers.set('Server-Timing', 'phase;desc="BYPASS-METHOD"');

    return new Response(resForClient.body, {
      status: resForClient.status,
      statusText: resForClient.statusText,
      headers
    });
  }
};
