/**
 * Cache Warming for CloudFlare Worker
 * Pre-loads frequently accessed endpoints to ensure fast first requests
 */

// Add this to your worker code
async function warmCache(env) {
  const WARM_ENDPOINTS = [
    '/health',
    '/api/health',
    '/api/lawyers',
    '/api/public/info'
  ];

  console.log('🔥 Warming cache for frequently accessed endpoints...');

  for (const endpoint of WARM_ENDPOINTS) {
    try {
      // Make a request to populate the cache
      const warmUrl = `https://api.aimthelaw.co.za${endpoint}`;
      await fetch(warmUrl);
      console.log(`✅ Warmed cache for ${endpoint}`);
    } catch (error) {
      console.error(`❌ Failed to warm ${endpoint}:`, error);
    }
  }
}

// Add to your worker's scheduled handler
export default {
  async scheduled(event, env, ctx) {
    // Run cache warming every 30 minutes
    ctx.waitUntil(warmCache(env));
  },

  // Your existing fetch handler
  async fetch(request, env, ctx) {
    // ... existing code
  }
};
