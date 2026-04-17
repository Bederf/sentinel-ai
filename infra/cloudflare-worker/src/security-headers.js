/**
 * Enhanced Security Headers for Legal Platform
 * Adds comprehensive security headers to all responses
 */

export const SECURITY_HEADERS = {
  // Attorney-Client Privilege Protection
  'X-Attorney-Client-Privilege': 'Protected',
  'X-Data-Classification': 'Legal-Confidential',

  // Standard Security Headers
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '1; mode=block',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',

  // HSTS for SSL enforcement
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',

  // CSP for XSS prevention
  'Content-Security-Policy': `
    default-src 'self' *.aimthelaw.co.za;
    script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data: static.cloudflareinsights.com https://cdn.jsdelivr.net;
    style-src 'self' 'unsafe-inline' fonts.googleapis.com;
    font-src 'self' fonts.gstatic.com;
    img-src 'self' data: https:;
    connect-src 'self'
      https://app.aimthelaw.co.za
      https://api.aimthelaw.co.za
      wss://app.aimthelaw.co.za
      wss://api.aimthelaw.co.za
      https://cloudflareinsights.com
      https://unpkg.com
      https://cdn.jsdelivr.net
      https://*.supabase.co
      https://api.elevenlabs.io
      wss://api.elevenlabs.io;
    media-src 'self' blob: data:;
    worker-src 'self' blob:;
    frame-ancestors 'none';
    base-uri 'self';
    form-action 'self';
    upgrade-insecure-requests;
  `.replace(/\s+/g, ' ').trim()
};

// Apply to all responses
export function addSecurityHeaders(response) {
  const newHeaders = new Headers(response.headers);

  Object.entries(SECURITY_HEADERS).forEach(([key, value]) => {
    newHeaders.set(key, value);
  });

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders
  });
}
