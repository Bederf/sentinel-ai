/**
 * AimTheLaw Minimal Cloudflare Worker - FIXED VERSION
 * Non-breaking performance enhancement layer
 */

// Minimal security headers
const MINIMAL_SECURITY_HEADERS = {
  'X-Powered-By': 'AimTheLaw-Edge',
  'X-Cache-Status': 'CLOUDFLARE'
};

// Cache configuration
const SAFE_CACHE_PATHS = [
  '/health',
  '/api/health',
  '/api/lawyers',
  '/api/status',
  '/api/public/info',
  '/api/public/contact'
];

const CACHE_DURATIONS = {
  '/health': 60,
  '/api/health': 60,
  '/api/lawyers': 300,
  '/api/status': 30,
  '/api/public/info': 600,
  '/api/public/contact': 600
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // IMPORTANT: When accessed via workers.dev, we need to forward to the actual origin
    // Replace the host if it's a workers.dev request
    if (url.hostname.includes('workers.dev')) {
      // For workers.dev requests, forward to the actual API
      url.hostname = 'api.aimthelaw.co.za';
      url.protocol = 'https:';
      request = new Request(url.toString(), request);
    }

    try {
      // Check if we should cache this request
      if (request.method === 'GET' && SAFE_CACHE_PATHS.includes(url.pathname)) {
        return await handleCachedRequest(request, env, url, ctx);
      }

      // Pass through all other requests
      return await passThrough(request);

    } catch (error) {
      console.error('Worker error:', error);
      // Always fall back to origin on error
      return await passThrough(request);
    }
  }
};

async function handleCachedRequest(request, env, url, ctx) {
  const cacheKey = `cache:${url.pathname}`;
  const cacheDuration = CACHE_DURATIONS[url.pathname] || 60;

  try {
    // Try cache first if KV is available
    if (env.MY_APP_STORAGE) {
      const cached = await env.MY_APP_STORAGE.get(cacheKey);

      if (cached) {
        return new Response(cached, {
          headers: {
            ...MINIMAL_SECURITY_HEADERS,
            'Content-Type': 'application/json',
            'Cache-Control': `public, max-age=${cacheDuration}`,
            'X-Cache': 'HIT'
          }
        });
      }
    }

    // Cache miss - fetch from origin
    const response = await fetch(request);
    const responseText = await response.text();

    // Store in cache if successful
    if (response.ok && env.MY_APP_STORAGE) {
      ctx.waitUntil(
        env.MY_APP_STORAGE.put(cacheKey, responseText, {
          expirationTtl: cacheDuration
        }).catch(err => console.error('Cache write error:', err))
      );
    }

    // Return response with our headers
    return new Response(responseText, {
      status: response.status,
      statusText: response.statusText,
      headers: {
        ...Object.fromEntries(response.headers),
        ...MINIMAL_SECURITY_HEADERS,
        'X-Cache': 'MISS'
      }
    });

  } catch (error) {
    console.error('Cache error:', error);
    return await passThrough(request);
  }
}

async function passThrough(request) {
  try {
    const response = await fetch(request);

    // Clone the response so we can modify headers
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: {
        ...Object.fromEntries(response.headers),
        ...MINIMAL_SECURITY_HEADERS
      }
    });
  } catch (error) {
    console.error('Passthrough error:', error);
    // Return error response
    return new Response('Gateway Error', {
      status: 502,
      headers: MINIMAL_SECURITY_HEADERS
    });
  }
}
