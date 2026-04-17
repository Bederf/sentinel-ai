/**
 * Geographic Access Control for Legal Compliance
 * Blocks access from certain countries and adds location-based headers
 */

export class GeoProtection {
  constructor() {
    // Countries to block for compliance reasons
    this.blockedCountries = ['CN', 'RU', 'KP', 'IR'];

    // Endpoints that require geographic restrictions
    this.restrictedEndpoints = [
      '/api/clients',
      '/api/cases',
      '/api/documents',
      '/api/billing'
    ];
  }

  checkAccess(request) {
    const country = request.cf?.country || 'unknown';
    const url = new URL(request.url);

    // Check if endpoint is restricted
    const isRestricted = this.restrictedEndpoints.some(
      ep => url.pathname.startsWith(ep)
    );

    if (isRestricted && this.blockedCountries.includes(country)) {
      return {
        allowed: false,
        reason: 'Geographic restriction',
        country: country
      };
    }

    // South African legal requirement - warn about cross-border data
    const isCrossBorder = country !== 'ZA';

    return {
      allowed: true,
      country: country,
      crossBorder: isCrossBorder,
      headers: {
        'X-Client-Country': country,
        'X-Data-Residency': isCrossBorder ? 'CROSS-BORDER' : 'DOMESTIC',
        'X-POPIA-Compliance': 'ENFORCED'
      }
    };
  }
}

// Usage in main worker
export default {
  async fetch(request, env, ctx) {
    const geoProtection = new GeoProtection();
    const geoCheck = geoProtection.checkAccess(request);

    if (!geoCheck.allowed) {
      return new Response('Access Denied - Geographic Restriction', {
        status: 403,
        headers: {
          'X-Blocked-Reason': geoCheck.reason,
          'X-Client-Country': geoCheck.country
        }
      });
    }

    // Process request normally
    const response = await handleRequest(request, env, ctx);

    // Add geo headers to response
    Object.entries(geoCheck.headers).forEach(([key, value]) => {
      response.headers.set(key, value);
    });

    return response;
  }
};
