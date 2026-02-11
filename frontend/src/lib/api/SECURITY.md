# API Security Guidelines (Phase 75-07)

## Preventing Token Exposure in Console Logs

This module implements multiple layers of protection to prevent accidental exposure of authentication tokens and sensitive data in browser console logs.

### 🔒 Security Measures

#### 1. **Refresh Token in Request Body (Not URL)**
- ✅ Refresh tokens sent in POST body: `{ refresh_token: "..." }`
- ❌ Never in URL query parameters
- Files: `client.ts` (frontend), `auth.py` (backend)

**Why:** URLs are logged in browser history, console, server logs, and proxy tools.

#### 2. **Sanitization Utilities**
- File: `security-utils.ts`
- Provides functions to sanitize logging before output:
  - `sanitizeForLogging()` - Remove JWT tokens and Bearer prefixes
  - `sanitizeUrl()` - Strip query parameters from URLs
  - `sanitizeHeaders()` - Remove Authorization headers
  - `sanitizeBody()` - Redact sensitive fields from request bodies
  - `secureConsoleLog` - Safe console methods that auto-sanitize

#### 3. **Secure Fetch Logging**
- Optional global fetch interceptor to log requests safely
- Only active in development mode
- Automatically sanitizes URLs and removes sensitive headers

#### 4. **Error Handling**
- Auth refresh errors logged with `secureConsoleLog.error()`
- Never logs the actual refresh token
- Safe for both development and production

### 📋 Usage Examples

**Safe console logging in API client code:**
```typescript
import { secureConsoleLog, sanitizeUrl } from './security-utils';

// Development only - automatically sanitizes
secureConsoleLog.log('API call to', sanitizeUrl(url));
secureConsoleLog.error('Auth failed');

// Never do this:
// console.log('Token:', token);  // ❌ DANGEROUS
// console.log('URL:', fullUrl);  // ❌ Exposes query params
```

**Sanitizing before external logging:**
```typescript
import { sanitizeBody, sanitizeHeaders } from './security-utils';

const safeRequest = {
  method: 'POST',
  url: sanitizeUrl(requestUrl),
  headers: sanitizeHeaders(requestHeaders),
  body: sanitizeBody(requestBody),
};

// Now safe to send to logging service
sendToExternalLogger(safeRequest);
```

### ⚠️ What NOT to Do

```typescript
// ❌ NEVER log these directly:
console.log(token);                    // Exposes JWT
console.log(refreshToken);             // Exposes refresh token
console.log(fullUrl);                  // May contain ?token=...
console.log(requestHeaders);           // Contains Authorization
console.log(requestBody);              // May contain tokens
console.log('Token:', localStorage);   // Exposes storage contents
```

### 🛡️ Production Considerations

**In production environment:**
1. All console output is disabled (see `security-utils.ts`)
2. Tokens are never logged at any level
3. Error messages are generic and safe
4. XHR requests log only sanitized URLs

**To enable aggressive console blocking in production:**
```typescript
// In App.tsx or main.tsx, uncomment:
if (!import.meta.env.DEV) {
  window.console.log = () => {};
  window.console.debug = () => {};
  window.console.info = () => {};
  // Keep .warn and .error for critical alerts
}
```

### 🔍 Security Audit Checklist

- [ ] No `console.log()` of tokens, refresh_token, or full URLs
- [ ] All API calls use `secureConsoleLog` or `sanitizeForLogging()`
- [ ] Refresh tokens sent in request body, never in URL
- [ ] Authorization headers removed from logged requests
- [ ] Error messages sanitized before display
- [ ] localStorage never logged directly
- [ ] Third-party logging services receive sanitized data

### 📚 Related Files

- `client.ts` - Core HTTP utilities with token management
- `security-utils.ts` - Sanitization and secure logging functions
- `auth.py` (backend) - Auth endpoints updated to accept tokens in body
- `CLAUDE.md` - Security section updated with guidelines

### 🚨 If You See Tokens in Console

**Report immediately:**
1. Note the exact console output
2. Check which file/function logged it
3. Update that code to use `secureConsoleLog`
4. Add sanitization wrapper if needed

**Quick fix template:**
```typescript
// Before (❌ UNSAFE):
console.log('Auth response:', response);

// After (✅ SAFE):
import { sanitizeBody } from '@/lib/api/security-utils';
secureConsoleLog.log('Auth response:', sanitizeBody(response));
```

---

**Phase 75-07**: Security hardening to prevent token exposure in logs
**Last Updated**: 2026-02-11
