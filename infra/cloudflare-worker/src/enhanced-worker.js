/**
 * AimTheLaw Enhanced CloudFlare Worker
 * Complete production-ready worker with all security features
 */

// ============================================
// CONFIGURATION
// ============================================

const CONFIG = {
  // Cache settings
  CACHE_PATHS: [
    '/health',
    '/api/health',
    '/api/lawyers',
    '/api/status',
    '/api/public/info',
    '/api/public/contact'
  ],

  CACHE_DURATIONS: {
    '/health': 60,
    '/api/health': 60,
    '/api/lawyers': 300,
    '/api/status': 30,
    '/api/public/info': 600,
    '/api/public/contact': 600
  },

  // Security settings
  BLOCKED_COUNTRIES: ['CN', 'RU', 'KP', 'IR', 'SY'],

  // Rate limits (requests per window in seconds)
  RATE_LIMITS: {
    '/api/auth': { requests: 5, window: 3600 },
    '/api/login': { requests: 5, window: 3600 },
    '/api/search': { requests: 50, window: 60 },
    '/api/documents': { requests: 30, window: 60 },
    'default': { requests: 100, window: 60 }
  },

  // Sensitive endpoints for audit logging
  SENSITIVE_ENDPOINTS: [
    '/api/clients',
    '/api/cases',
    '/api/documents',
    '/api/billing',
    '/api/invoices'
  ]
};

// ============================================
// SECURITY HEADERS
// ============================================

const SECURITY_HEADERS = {
  // Legal compliance headers
  'X-Attorney-Client-Privilege': 'Protected',
  'X-Data-Classification': 'Legal-Confidential',
  'X-POPIA-Compliance': 'Enforced',

  // Standard security
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '1; mode=block',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',

  // Worker identification
  'X-Powered-By': 'AimTheLaw-Edge-v2',
  'X-Worker-Version': 'v2.0'
};

// ============================================
// RATE LIMITER
// ============================================

class RateLimiter {
  constructor(env) {
    this.storage = env.MY_APP_STORAGE;
  }

  async check(request) {
    const url = new URL(request.url);
    const clientIp = request.headers.get('CF-Connecting-IP') || 'unknown';
    const endpoint = this.getEndpointKey(url.pathname);
    const limit = CONFIG.RATE_LIMITS[endpoint] || CONFIG.RATE_LIMITS.default;

    const key = `ratelimit:${clientIp}:${endpoint}`;

    try {
      const current = await this.storage?.get(key);
      const count = current ? parseInt(current) : 0;

      if (count >= limit.requests) {
        return { allowed: false, remaining: 0, resetIn: limit.window };
      }

      if (this.storage) {
        await this.storage.put(key, (count + 1).toString(), {
          expirationTtl: limit.window
        });
      }

      return {
        allowed: true,
        remaining: limit.requests - count - 1,
        resetIn: limit.window
      };
    } catch (error) {
      console.error('Rate limit error:', error);
      return { allowed: true, remaining: 999, resetIn: 60 };
    }
  }

  getEndpointKey(pathname) {
    for (const [key, _] of Object.entries(CONFIG.RATE_LIMITS)) {
      if (key !== 'default' && pathname.startsWith(key)) {
        return key;
      }
    }
    return 'default';
  }
}

// ============================================
// GEO PROTECTION
// ============================================

class GeoProtection {
  check(request) {
    const country = request.cf?.country || 'unknown';
    const url = new URL(request.url);

    // Check if country is blocked
    if (CONFIG.BLOCKED_COUNTRIES.includes(country)) {
      // Allow health checks even from blocked countries
      if (url.pathname === '/health' || url.pathname === '/api/health') {
        return { allowed: true, country };
      }

      return {
        allowed: false,
        reason: `Access denied from ${country}`,
        country
      };
    }

    return {
      allowed: true,
      country,
      isCrossBorder: country !== 'ZA'
    };
  }
}

// ============================================
// AUDIT LOGGER
// ============================================

class AuditLogger {
  constructor(env) {
    this.storage = env.MY_APP_STORAGE;
    this.database = env.MY_APP_DATABASE;
  }

  async log(request, response, userId = null) {
    const url = new URL(request.url);

    // Only log sensitive endpoints
    const isSensitive = CONFIG.SENSITIVE_ENDPOINTS.some(
      ep => url.pathname.startsWith(ep)
    );

    if (!isSensitive) return;

    const entry = {
      timestamp: new Date().toISOString(),
      method: request.method,
      path: url.pathname,
      status: response.status,
      ip: request.headers.get('CF-Connecting-IP'),
      country: request.cf?.country,
      userAgent: request.headers.get('User-Agent'),
      userId: userId || this.extractUserId(request)
    };

    // Store in KV for quick access
    if (this.storage) {
      const key = `audit:${Date.now()}:${Math.random()}`;
      await this.storage.put(key, JSON.stringify(entry), {
        expirationTtl: 7 * 24 * 60 * 60 // 7 days
      });
    }

    // Also log to D1 if available
    if (this.database) {
      try {
        await this.database.prepare(`
          INSERT INTO audit_logs (timestamp, method, path, status, ip, country, user_id)
          VALUES (?, ?, ?, ?, ?, ?, ?)
        `).bind(
          entry.timestamp,
          entry.method,
          entry.path,
          entry.status,
          entry.ip,
          entry.country,
          entry.userId
        ).run();
      } catch (error) {
        console.error('D1 audit log failed:', error);
      }
    }

    // Alert on failures
    if (response.status >= 400) {
      console.warn('⚠️ Failed request:', entry);
    }
  }

  extractUserId(request) {
    const auth = request.headers.get('Authorization');
    if (!auth) return null;

    try {
      if (auth.startsWith('Bearer ')) {
        const token = auth.substring(7);
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.sub || payload.user_id || null;
      }
    } catch {
      return null;
    }
    return null;
  }
}

// ============================================
// CACHE HANDLER
// ============================================

async function handleCachedRequest(request, env, url, ctx) {
  const cacheKey = `cache:${url.pathname}`;
  const cacheDuration = CONFIG.CACHE_DURATIONS[url.pathname] || 60;

  try {
    // Check cache first
    if (env.MY_APP_STORAGE) {
      const cached = await env.MY_APP_STORAGE.get(cacheKey);

      if (cached) {
        console.log(`Cache HIT: ${url.pathname}`);

        return new Response(cached, {
          headers: {
            'Content-Type': 'application/json',
            'Cache-Control': `public, max-age=${cacheDuration}`,
            'X-Cache': 'HIT',
            'X-Cache-Age': 'fresh',
            ...SECURITY_HEADERS
          }
        });
      }
    }

    console.log(`Cache MISS: ${url.pathname}`);

    // Fetch from origin
    const response = await fetch(request);
    const responseText = await response.text();

    // Store in cache if successful
    if (response.ok && env.MY_APP_STORAGE) {
      ctx.waitUntil(
        env.MY_APP_STORAGE.put(cacheKey, responseText, {
          expirationTtl: cacheDuration
        })
      );
    }

    return new Response(responseText, {
      status: response.status,
      headers: {
        ...Object.fromEntries(response.headers),
        'X-Cache': 'MISS',
        ...SECURITY_HEADERS
      }
    });

  } catch (error) {
    console.error('Cache handler error:', error);
    return fetch(request);
  }
}

// ============================================
// MAIN WORKER HANDLER
// ============================================

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const startTime = Date.now();

    try {
      // 1. GEO BLOCKING
      const geoProtection = new GeoProtection();
      const geoCheck = geoProtection.check(request);

      if (!geoCheck.allowed) {
        console.log(`Blocked: ${geoCheck.country} - ${geoCheck.reason}`);
        return new Response('Access Denied', {
          status: 403,
          headers: {
            'X-Blocked-Reason': geoCheck.reason,
            'X-Client-Country': geoCheck.country,
            ...SECURITY_HEADERS
          }
        });
      }

      // 2. RATE LIMITING
      const rateLimiter = new RateLimiter(env);
      const rateCheck = await rateLimiter.check(request);

      if (!rateCheck.allowed) {
        console.log(`Rate limited: ${url.pathname}`);
        return new Response('Too Many Requests', {
          status: 429,
          headers: {
            'Retry-After': rateCheck.resetIn.toString(),
            'X-RateLimit-Limit': '100',
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': rateCheck.resetIn.toString(),
            ...SECURITY_HEADERS
          }
        });
      }

      // 3. HANDLE REQUEST
      let response;

      // Check if this is a cacheable endpoint
      if (request.method === 'GET' && CONFIG.CACHE_PATHS.includes(url.pathname)) {
        response = await handleCachedRequest(request, env, url, ctx);
      } else {
        // Pass through to origin
        response = await fetch(request);

        // Add security headers
        const newHeaders = new Headers(response.headers);
        Object.entries(SECURITY_HEADERS).forEach(([key, value]) => {
          newHeaders.set(key, value);
        });

        response = new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders
        });
      }

      // 4. AUDIT LOGGING
      const auditLogger = new AuditLogger(env);
      ctx.waitUntil(auditLogger.log(request, response));

      // 5. ADD PERFORMANCE HEADERS
      const processingTime = Date.now() - startTime;
      response.headers.set('X-Processing-Time', `${processingTime}ms`);
      response.headers.set('X-Client-Country', geoCheck.country);
      response.headers.set('X-RateLimit-Remaining', rateCheck.remaining.toString());

      if (geoCheck.isCrossBorder) {
        response.headers.set('X-Data-Residency', 'CROSS-BORDER');
        response.headers.set('X-POPIA-Notice', 'Cross-border data transfer in effect');
      }

      return response;

    } catch (error) {
      console.error('Worker error:', error);

      // Return a safe error response
      return new Response('Internal Server Error', {
        status: 500,
        headers: SECURITY_HEADERS
      });
    }
  },

  // SCHEDULED HANDLER FOR CACHE WARMING
  async scheduled(event, env, ctx) {
    console.log('🔥 Starting scheduled cache warming...');

    const endpoints = CONFIG.CACHE_PATHS;

    for (const endpoint of endpoints) {
      try {
        const url = `https://api.aimthelaw.co.za${endpoint}`;
        await fetch(url);
        console.log(`✅ Warmed: ${endpoint}`);
      } catch (error) {
        console.error(`❌ Failed to warm ${endpoint}:`, error);
      }
    }

    console.log('✅ Cache warming complete');
  }
};
