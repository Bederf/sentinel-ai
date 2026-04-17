/**
 * Simple Rate Limiter for CloudFlare Worker
 * Protects API from abuse using KV storage
 */

export class RateLimiter {
  constructor(env) {
    this.storage = env.MY_APP_STORAGE;
    this.limits = {
      '/api/auth': { requests: 5, window: 3600 },     // 5 requests per hour
      '/api/search': { requests: 50, window: 60 },    // 50 requests per minute
      'default': { requests: 100, window: 60 }        // 100 requests per minute
    };
  }

  async checkLimit(request) {
    const url = new URL(request.url);
    const clientIp = request.headers.get('CF-Connecting-IP') || 'unknown';
    const endpoint = this.getEndpointKey(url.pathname);
    const limit = this.limits[endpoint] || this.limits.default;

    const key = `ratelimit:${clientIp}:${endpoint}`;

    try {
      // Get current count
      const current = await this.storage.get(key);
      const count = current ? parseInt(current) : 0;

      if (count >= limit.requests) {
        return {
          allowed: false,
          remaining: 0,
          resetIn: limit.window
        };
      }

      // Increment counter
      await this.storage.put(key, (count + 1).toString(), {
        expirationTtl: limit.window
      });

      return {
        allowed: true,
        remaining: limit.requests - count - 1,
        resetIn: limit.window
      };
    } catch (error) {
      console.error('Rate limit check failed:', error);
      // Fail open - allow request if rate limiting fails
      return { allowed: true, remaining: 999, resetIn: 60 };
    }
  }

  getEndpointKey(pathname) {
    // Map paths to rate limit keys
    if (pathname.startsWith('/api/auth')) return '/api/auth';
    if (pathname.includes('/search')) return '/api/search';
    return 'default';
  }
}

// Usage in your main worker:
export default {
  async fetch(request, env, ctx) {
    const rateLimiter = new RateLimiter(env);
    const { allowed, remaining, resetIn } = await rateLimiter.checkLimit(request);

    if (!allowed) {
      return new Response('Too Many Requests', {
        status: 429,
        headers: {
          'X-RateLimit-Limit': '100',
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': resetIn.toString(),
          'Retry-After': resetIn.toString()
        }
      });
    }

    // Continue with normal processing
    const response = await handleRequest(request, env, ctx);

    // Add rate limit headers to response
    response.headers.set('X-RateLimit-Remaining', remaining.toString());

    return response;
  }
};
