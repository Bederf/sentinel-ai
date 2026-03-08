/**
 * Security Utilities - Prevent Accidental Logging of Sensitive Data
 *
 * This module provides safe logging functions that automatically sanitize:
 * - Authorization headers (Bearer tokens)
 * - Refresh tokens in request bodies
 * - API URLs (removes query parameters)
 * - JWT tokens in any form
 *
 * Phase 75-07: Security hardening to prevent token exposure in logs
 */

// Patterns that indicate sensitive data
const SENSITIVE_PATTERNS = [
  /Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi, // JWT tokens in Authorization header
  /refresh_token["\s:=]+[A-Za-z0-9\-._~+/]+=*/gi, // refresh_token fields
  /access_token["\s:=]+[A-Za-z0-9\-._~+/]+=*/gi, // access_token fields
  /token["\s:=]+[A-Za-z0-9\-._~+/]+=*/gi, // generic token fields
  /eyJ[A-Za-z0-9\-._~+/]+=*/g, // JWT format (starts with eyJ when base64 encoded)
];

/**
 * Sanitize a string by replacing sensitive data with [REDACTED]
 */
export function sanitizeForLogging(text: string): string {
  if (typeof text !== 'string') return text;

  let sanitized = text;
  for (const pattern of SENSITIVE_PATTERNS) {
    sanitized = sanitized.replace(pattern, '[REDACTED]');
  }
  return sanitized;
}

/**
 * Sanitize a URL by removing query parameters that might contain tokens
 */
export function sanitizeUrl(url: string): string {
  try {
    const urlObj = new URL(url);
    // Remove all query parameters
    if (urlObj.search) {
      urlObj.search = '';
    }
    return urlObj.toString();
  } catch {
    // If URL parsing fails, return as-is (relative URLs, etc.)
    return sanitizeForLogging(url);
  }
}

/**
 * Sanitize request headers by removing Authorization header
 */
export function sanitizeHeaders(headers: HeadersInit | Record<string, string>): Record<string, string> {
  const sanitized: Record<string, string> = {};

  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      if (key.toLowerCase() !== 'authorization') {
        sanitized[key] = sanitizeForLogging(value);
      }
    });
  } else if (typeof headers === 'object') {
    for (const [key, value] of Object.entries(headers)) {
      if (key.toLowerCase() !== 'authorization') {
        sanitized[key] = sanitizeForLogging(String(value));
      }
    }
  }

  return sanitized;
}

/**
 * Sanitize request body by removing sensitive fields
 */
export function sanitizeBody(body: any): any {
  if (!body) return body;

  try {
    if (typeof body === 'string') {
      // Try to parse as JSON
      try {
        const parsed = JSON.parse(body);
        return sanitizeObject(parsed);
      } catch {
        // Not JSON, just sanitize string
        return sanitizeForLogging(body);
      }
    }

    if (typeof body === 'object') {
      return sanitizeObject(body);
    }

    return body;
  } catch {
    return '[SANITIZATION_ERROR]';
  }
}

/**
 * Recursively sanitize an object by removing/redacting sensitive fields
 */
function sanitizeObject(obj: any, depth = 0): any {
  if (depth > 10) return '[MAX_DEPTH_EXCEEDED]'; // Prevent infinite recursion

  if (obj === null || obj === undefined) return obj;

  if (typeof obj !== 'object') {
    return sanitizeForLogging(String(obj));
  }

  if (Array.isArray(obj)) {
    return obj.map((item) => sanitizeObject(item, depth + 1));
  }

  const sanitized: Record<string, any> = {};
  for (const [key, value] of Object.entries(obj)) {
    const lowerKey = key.toLowerCase();

    // Redact sensitive field names
    if (
      lowerKey.includes('token') ||
      lowerKey.includes('password') ||
      lowerKey.includes('secret') ||
      lowerKey.includes('credential') ||
      lowerKey.includes('key')
    ) {
      sanitized[key] = '[REDACTED]';
    } else if (typeof value === 'string') {
      sanitized[key] = sanitizeForLogging(value);
    } else if (typeof value === 'object') {
      sanitized[key] = sanitizeObject(value, depth + 1);
    } else {
      sanitized[key] = value;
    }
  }

  return sanitized;
}

/**
 * Safe console.log that sanitizes sensitive data
 * Only logs in development mode
 */
export const secureConsoleLog = {
  log: (message: string, ...args: any[]) => {
    if (import.meta.env.DEV) {
      console.log(sanitizeForLogging(message), ...args.map(sanitizeBody));
    }
  },

  error: (message: string, ...args: any[]) => {
    if (import.meta.env.DEV) {
      console.error(sanitizeForLogging(message), ...args.map(sanitizeBody));
    }
  },

  warn: (message: string, ...args: any[]) => {
    if (import.meta.env.DEV) {
      console.warn(sanitizeForLogging(message), ...args.map(sanitizeBody));
    }
  },

  debug: (message: string, ...args: any[]) => {
    if (import.meta.env.DEV) {
      console.debug(sanitizeForLogging(message), ...args.map(sanitizeBody));
    }
  },
};

/**
 * Disable default console methods to prevent accidental logging of tokens
 * WARNING: This is aggressive and should only be used in production
 *
 * Uncomment in production to prevent ANY console output:
 * ```typescript
 * if (!import.meta.env.DEV) {
 *   window.console.log = () => {};
 *   window.console.debug = () => {};
 * }
 * ```
 */

/**
 * Hook into global fetch to prevent console logging of auth headers
 * This intercepts XHR logs that might expose tokens
 */
export function enableSecureFetchLogging(): void {
  const originalFetch = window.fetch;

  window.fetch = function (...args: Parameters<typeof fetch>) {
    const [resource, config] = args;

    // Only log in development with sanitization
    if (import.meta.env.DEV) {
      const method = (config?.method || 'GET').toUpperCase();
      const url = typeof resource === 'string' ? resource : (resource as any).url;
      const sanitizedUrl = sanitizeUrl(url);

      // Log request (without sensitive headers)
      secureConsoleLog.debug(`[FETCH] ${method} ${sanitizedUrl}`);
    }

    return originalFetch.apply(this, args);
  };
}

/**
 * Initialize security protections at app startup
 * Call this from your main App component to enable production safeguards
 */
export function initializeSecurityProtections(): void {
  // Production: Disable console methods to prevent accidental token logging
  if (!import.meta.env.DEV) {
    // Keep warn and error for critical alerts, disable info/debug/log
    const originalLog = console.log;
    const _originalDebug = console.debug;
    const _originalInfo = console.info;

    console.log = () => {};
    console.debug = () => {};
    console.info = () => {};

    // Keep error and warn for critical alerts only
    console.error = (message: string, ...args: any[]) => {
      const sanitized = sanitizeForLogging(message);
      originalLog('%cCRITICAL ERROR:', 'color: red; font-weight: bold;', sanitized, ...args);
    };

    console.warn = (message: string, ...args: any[]) => {
      const sanitized = sanitizeForLogging(message);
      originalLog('%cWARNING:', 'color: orange; font-weight: bold;', sanitized, ...args);
    };
  }

  // Development: Enable secure fetch logging for debugging
  if (import.meta.env.DEV) {
    // Uncomment to debug API calls with sanitization:
    // enableSecureFetchLogging();
  }
}

// Enable secure fetch logging on module load
if (import.meta.env.DEV) {
  // Only enable in development to avoid performance impact
  // Uncomment to debug fetch calls safely:
  // enableSecureFetchLogging();
}
